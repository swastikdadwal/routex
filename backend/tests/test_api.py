"""End-to-end API tests against a real PostgreSQL test database."""
import os
import time
from pathlib import Path

import pytest
from dotenv import dotenv_values

_values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
if "TEST_DATABASE_URL" not in _values:
    pytest.skip("TEST_DATABASE_URL is not set in backend/.env", allow_module_level=True)
os.environ["DATABASE_URL"] = _values["TEST_DATABASE_URL"]

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

ALL = ["greedy", "dp", "brute", "bnb", "approx"]


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client


def wait_for_run(client, run_id, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "distances", "solving"):
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def scenario(client, orders=6, seed=1):
    response = client.post("/api/sample", json={"city": "Bengaluru", "orders": orders, "seed": seed})
    assert response.status_code == 201
    return response.json()["warehouse_id"]


def test_crud_persists_and_validates(client):
    vehicle = client.post("/api/vehicles", json={"name": "Van", "capacity": 8, "cost_per_km": 1.2}).json()
    assert client.patch(f"/api/vehicles/{vehicle['id']}", json={"capacity": 9}).json()["capacity"] == 9
    assert client.post("/api/vehicles", json={"name": "Bad", "capacity": 0}).status_code == 422

    order = client.post("/api/orders", json={"lat": 12.9, "lng": 77.6, "demand": 2}).json()
    assert order["label"] == f"Order {order['id']}"
    assert client.patch(f"/api/orders/{order['id']}", json={"label": "Asha", "demand": 4}).json()["demand"] == 4
    assert client.post("/api/orders", json={"lat": 120, "lng": 77.6}).status_code == 422
    assert client.delete(f"/api/orders/{order['id']}").status_code == 204
    assert client.get("/api/orders").json() == []
    assert client.patch("/api/orders/99999", json={"demand": 1}).status_code == 404


def test_run_compares_all_algorithms_and_saves_results(client):
    warehouse = scenario(client)
    created = client.post(
        "/api/runs", json={"warehouse_id": warehouse, "algorithms": ALL, "distance_source": "straight"}
    )
    assert created.status_code == 201
    run = wait_for_run(client, created.json()["id"])
    assert run["status"] == "done"
    results = {r["algorithm"]: r for r in run["results"]}
    assert set(results) == set(ALL)
    assert results["dp"]["status"] == results["bnb"]["status"] == results["brute"]["status"] == "optimal"
    optimum = results["dp"]["distance_m"]
    assert results["bnb"]["distance_m"] == pytest.approx(optimum)
    assert results["brute"]["distance_m"] == pytest.approx(optimum)
    assert results["greedy"]["distance_m"] >= optimum - 1e-6
    assert run["lower_bound_m"] <= optimum + 1e-6
    capacities = [v["capacity"] for v in run["scenario"]["vehicles"]]
    for route in results["dp"]["routes"]:
        assert route["load"] <= capacities[route["vehicle_index"]]


def test_past_run_survives_scenario_edits(client):
    warehouse = scenario(client)
    run_id = client.post(
        "/api/runs", json={"warehouse_id": warehouse, "algorithms": ["greedy"], "distance_source": "straight"}
    ).json()["id"]
    wait_for_run(client, run_id)
    assert client.delete("/api/orders").status_code == 204
    run = client.get(f"/api/runs/{run_id}").json()
    assert len(run["scenario"]["orders"]) == 6
    assert run["results"][0]["routes"]


def test_large_scenario_skips_exact_solvers_and_respects_limit(client):
    warehouse = scenario(client, orders=25)
    for vehicle in client.get("/api/vehicles").json():
        client.patch(f"/api/vehicles/{vehicle['id']}", json={"capacity": 40})
    run_id = client.post(
        "/api/runs",
        json={"warehouse_id": warehouse, "algorithms": ALL, "distance_source": "straight", "time_limit_s": 1},
    ).json()["id"]
    run = wait_for_run(client, run_id)
    results = {r["algorithm"]: r for r in run["results"]}
    assert results["dp"]["status"] == "skipped" and results["brute"]["status"] == "skipped"
    assert results["bnb"]["status"] == "time_limit" and results["bnb"]["distance_m"]


def test_cancel_stops_a_long_search_and_keeps_fast_results(client):
    warehouse = scenario(client, orders=30)
    for vehicle in client.get("/api/vehicles").json():
        client.patch(f"/api/vehicles/{vehicle['id']}", json={"capacity": 40})
    run_id = client.post(
        "/api/runs",
        json={"warehouse_id": warehouse, "algorithms": ["greedy", "approx", "bnb"], "distance_source": "straight", "time_limit_s": 60},
    ).json()["id"]
    deadline = time.time() + 30
    while time.time() < deadline and len(client.get(f"/api/runs/{run_id}").json()["results"]) < 2:
        time.sleep(0.1)
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    run = wait_for_run(client, run_id, seconds=10)
    assert run["status"] == "cancelled"
    assert {r["algorithm"] for r in run["results"]} == {"greedy", "approx"}


def test_overloaded_fleet_reports_unassigned_orders(client):
    warehouse = scenario(client)
    vehicles = client.get("/api/vehicles").json()
    for vehicle in vehicles:
        client.patch(f"/api/vehicles/{vehicle['id']}", json={"capacity": 3})
    orders = client.get("/api/orders").json()
    for order in orders:
        client.patch(f"/api/orders/{order['id']}", json={"demand": 2})
    response = client.post(
        "/api/runs", json={"warehouse_id": warehouse, "algorithms": ALL, "distance_source": "straight"}
    )
    assert response.status_code == 201
    run = wait_for_run(client, response.json()["id"])
    results = {r["algorithm"]: r for r in run["results"]}
    for name in ("greedy", "approx"):
        assert results[name]["status"] == "incomplete"
        assert results[name]["routes"] and results[name]["unserved"]
        served = sum(len(route["stops"]) for route in results[name]["routes"])
        assert served + len(results[name]["unserved"]) == len(orders)
        for route in results[name]["routes"]:
            assert route["load"] <= 3
    for name in ("dp", "bnb", "brute"):
        assert results[name]["status"] == "infeasible", name


def test_roadmap_endpoints(client):
    points = [{"lat": 12.97, "lng": 77.59}, {"lat": 12.98, "lng": 77.60}]
    matrix = client.post("/api/distance-matrix", json={"points": points, "source": "straight"}).json()
    assert matrix["source"] == "straight"
    assert matrix["matrix_m"][0][0] == 0 and matrix["matrix_m"][0][1] == matrix["matrix_m"][1][0] > 0
    assert client.post("/api/distance-matrix", json={"points": points[:1]}).status_code == 422

    warehouse = scenario(client)
    body = {"warehouse_id": warehouse, "distance_source": "straight"}
    one = client.post("/api/optimize", json={**body, "algorithm": "dp"})
    assert one.status_code == 201
    assert [r["algorithm"] for r in wait_for_run(client, one.json()["id"])["results"]] == ["dp"]
    compared = client.post("/api/compare", json={**body, "algorithms": ["greedy", "dp"]})
    assert compared.status_code == 201
    assert len(wait_for_run(client, compared.json()["id"])["results"]) == 2
    assert {r["id"] for r in client.get("/api/results").json()} == {one.json()["id"], compared.json()["id"]}


def test_run_rejects_invalid_requests(client):
    warehouse = scenario(client)
    vehicles = client.get("/api/vehicles").json()
    body = {"warehouse_id": warehouse, "algorithms": ["greedy"], "distance_source": "straight"}
    for vehicle in vehicles:
        client.patch(f"/api/vehicles/{vehicle['id']}", json={"active": False})
    assert "vehicle" in client.post("/api/runs", json=body).json()["detail"]
    assert client.post("/api/runs", json={**body, "algorithms": ["magic"]}).status_code == 422
