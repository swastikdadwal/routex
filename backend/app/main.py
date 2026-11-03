import math
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from . import road_data, runner, schemas, solver_process
from .algorithms.solvers import ALGORITHMS, BRUTE_FORCE_MAX_PLANS, DP_MAX_ORDERS
from .db import Base, engine, get_session
from .models import Benchmark, Order, Run, Vehicle, Warehouse

MAX_ORDERS = 40
MAX_VEHICLES = 8
CITIES = {
    "Bengaluru": (12.9716, 77.5946, 7.0),
    "Delhi": (28.6139, 77.209, 8.0),
    "Hyderabad": (17.385, 78.4867, 7.0),
    "London": (51.5074, -0.1278, 6.0),
    "Paris": (48.8566, 2.3522, 4.5),
}
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
ACTIVE_RUN_STATES = ("pending", "distances", "solving")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    runner.mark_interrupted()
    yield


app = FastAPI(title="RouteX", lifespan=lifespan)
api = APIRouter(prefix="/api")
Db = Depends(get_session)


def _get(session: Session, model, identifier: int):
    item = session.get(model, identifier)
    if item is None:
        raise HTTPException(404, f"{model.__name__} {identifier} not found")
    return item


def _apply(item, patch) -> None:
    for name, value in patch.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, name, value)


def _order_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Order))


@api.get("/meta")
def meta():
    return {
        "algorithms": ALGORITHMS,
        "cities": list(CITIES),
        "limits": {
            "orders": MAX_ORDERS,
            "vehicles": MAX_VEHICLES,
            "dp_orders": DP_MAX_ORDERS,
            "brute_force_plans": BRUTE_FORCE_MAX_PLANS,
        },
    }


# ---------------------------------------------------------------- Warehouses


@api.get("/warehouses", response_model=list[schemas.WarehouseOut])
def list_warehouses(session: Session = Db):
    return session.scalars(select(Warehouse).order_by(Warehouse.id)).all()


@api.post("/warehouses", response_model=schemas.WarehouseOut, status_code=201)
def create_warehouse(body: schemas.WarehouseIn, session: Session = Db):
    item = Warehouse(**body.model_dump())
    session.add(item)
    session.commit()
    return item


@api.patch("/warehouses/{identifier}", response_model=schemas.WarehouseOut)
def update_warehouse(identifier: int, body: schemas.WarehousePatch, session: Session = Db):
    item = _get(session, Warehouse, identifier)
    _apply(item, body)
    session.commit()
    return item


@api.delete("/warehouses/{identifier}", status_code=204)
def delete_warehouse(identifier: int, session: Session = Db):
    session.delete(_get(session, Warehouse, identifier))
    session.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ Vehicles


@api.get("/vehicles", response_model=list[schemas.VehicleOut])
def list_vehicles(session: Session = Db):
    return session.scalars(select(Vehicle).order_by(Vehicle.id)).all()


@api.post("/vehicles", response_model=schemas.VehicleOut, status_code=201)
def create_vehicle(body: schemas.VehicleIn, session: Session = Db):
    item = Vehicle(**body.model_dump())
    session.add(item)
    session.commit()
    return item


@api.patch("/vehicles/{identifier}", response_model=schemas.VehicleOut)
def update_vehicle(identifier: int, body: schemas.VehiclePatch, session: Session = Db):
    item = _get(session, Vehicle, identifier)
    _apply(item, body)
    session.commit()
    return item


@api.delete("/vehicles/{identifier}", status_code=204)
def delete_vehicle(identifier: int, session: Session = Db):
    session.delete(_get(session, Vehicle, identifier))
    session.commit()
    return Response(status_code=204)


# -------------------------------------------------------------------- Orders


@api.get("/orders", response_model=list[schemas.OrderOut])
def list_orders(session: Session = Db):
    return session.scalars(select(Order).order_by(Order.id)).all()


@api.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(body: schemas.OrderIn, session: Session = Db):
    if _order_count(session) >= MAX_ORDERS:
        raise HTTPException(409, f"RouteX handles up to {MAX_ORDERS} orders at a time.")
    values = body.model_dump()
    label = values.pop("label") or None
    item = Order(label=label or "Order", **values)
    session.add(item)
    session.flush()
    if label is None:
        item.label = f"Order {item.id}"
    session.commit()
    return item


@api.patch("/orders/{identifier}", response_model=schemas.OrderOut)
def update_order(identifier: int, body: schemas.OrderPatch, session: Session = Db):
    item = _get(session, Order, identifier)
    _apply(item, body)
    session.commit()
    return item


@api.delete("/orders/{identifier}", status_code=204)
def delete_order(identifier: int, session: Session = Db):
    session.delete(_get(session, Order, identifier))
    session.commit()
    return Response(status_code=204)


@api.delete("/orders", status_code=204)
def clear_orders(session: Session = Db):
    session.execute(delete(Order))
    session.commit()
    return Response(status_code=204)


# -------------------------------------------------------------------- Sample


@api.post("/sample", status_code=201)
def load_sample(body: schemas.SampleIn, session: Session = Db):
    """Adds a warehouse in the city, random orders, and a fleet if none exists."""
    if body.city not in CITIES:
        raise HTTPException(422, f"Unknown city {body.city}")
    room = MAX_ORDERS - _order_count(session)
    if body.orders > room:
        raise HTTPException(409, f"Only {room} more orders fit. Clear some orders first.")
    lat, lng, km = CITIES[body.city]
    rng = random.Random(body.seed)
    warehouse = Warehouse(name=f"{body.city} warehouse", lat=lat, lng=lng)
    session.add(warehouse)

    lat_span = km / 111.32
    lng_span = km / (111.32 * math.cos(math.radians(lat)))
    created = []
    for _ in range(body.orders):
        angle = rng.random() * 2 * math.pi
        reach = math.sqrt(0.04 + 0.96 * rng.random())
        order = Order(
            label="Order",
            lat=lat + math.sin(angle) * reach * lat_span,
            lng=lng + math.cos(angle) * reach * lng_span,
            demand=rng.randint(1, 3),
        )
        session.add(order)
        created.append(order)
    session.flush()
    for order in created:
        order.label = f"Order {order.id}"

    if session.scalar(select(func.count()).select_from(Vehicle)) == 0:
        # Sized to the orders, so no single vehicle can carry everything and the
        # sample always shows a real assignment decision.
        total = sum(order.demand for order in created)
        session.add_all(
            [
                Vehicle(name="Truck", capacity=max(3, math.ceil(total * 0.5)), cost_per_km=2.0),
                Vehicle(name="Van", capacity=max(3, math.ceil(total * 0.4)), cost_per_km=1.5),
                Vehicle(name="Bike", capacity=max(3, math.ceil(total * 0.3)), cost_per_km=0.5),
            ]
        )
    session.commit()
    return {"warehouse_id": warehouse.id, "orders": len(created)}


# ---------------------------------------------------------------------- Runs


def _load_run(session: Session, identifier: int) -> Run:
    run = session.scalar(select(Run).where(Run.id == identifier).options(selectinload(Run.results)))
    if run is None:
        raise HTTPException(404, f"Run {identifier} not found")
    return run


@api.post("/runs", response_model=schemas.RunOut, status_code=201)
@api.post("/compare", response_model=schemas.RunOut, status_code=201)
def create_run(body: schemas.RunIn, session: Session = Db):
    warehouse = _get(session, Warehouse, body.warehouse_id)
    orders = session.scalars(select(Order).order_by(Order.id)).all()
    vehicles = session.scalars(select(Vehicle).where(Vehicle.active).order_by(Vehicle.id)).all()
    if not orders:
        raise HTTPException(422, "Add at least one order first.")
    if not vehicles:
        raise HTTPException(422, "Register at least one active vehicle first.")
    if len(vehicles) > MAX_VEHICLES:
        raise HTTPException(422, f"RouteX compares up to {MAX_VEHICLES} active vehicles at a time.")

    run = Run(
        status="pending",
        scenario={
            "warehouse": {"id": warehouse.id, "name": warehouse.name, "lat": warehouse.lat, "lng": warehouse.lng},
            "orders": [{"id": o.id, "label": o.label, "lat": o.lat, "lng": o.lng, "demand": o.demand} for o in orders],
            "vehicles": [
                {"id": v.id, "name": v.name, "capacity": v.capacity, "cost_per_km": v.cost_per_km} for v in vehicles
            ],
        },
        algorithms=list(body.algorithms),
        requested_source=body.distance_source,
        time_limit_s=body.time_limit_s,
    )
    session.add(run)
    session.commit()
    runner.start_run(run.id)
    return _load_run(session, run.id)


@api.post("/optimize", response_model=schemas.RunOut, status_code=201)
def optimize(body: schemas.OptimizeIn, session: Session = Db):
    """One algorithm on the saved scenario. Poll GET /runs/{id} for its result."""
    return create_run(
        schemas.RunIn(
            warehouse_id=body.warehouse_id,
            algorithms=[body.algorithm],
            distance_source=body.distance_source,
            time_limit_s=body.time_limit_s,
        ),
        session,
    )


@api.get("/runs", response_model=list[schemas.RunOut])
@api.get("/results", response_model=list[schemas.RunOut])
def list_runs(session: Session = Db):
    query = select(Run).options(selectinload(Run.results)).order_by(Run.id.desc()).limit(50)
    return session.scalars(query).all()


@api.get("/runs/{identifier}", response_model=schemas.RunOut)
def get_run(identifier: int, session: Session = Db):
    return _load_run(session, identifier)


@api.post("/runs/{identifier}/cancel", response_model=schemas.RunOut)
def cancel_run(identifier: int, session: Session = Db):
    run = _load_run(session, identifier)
    if run.status in ACTIVE_RUN_STATES:
        runner.cancel("run", identifier)
    return run


@api.delete("/runs/{identifier}", status_code=204)
def delete_run(identifier: int, session: Session = Db):
    run = _load_run(session, identifier)
    if run.status in ACTIVE_RUN_STATES:
        raise HTTPException(409, "Stop this run before deleting it.")
    session.delete(run)
    session.commit()
    return Response(status_code=204)


@api.post("/distance-matrix")
def distance_matrix(body: schemas.DistanceMatrixIn):
    matrix, used, stats, notice = road_data.distance_matrix([p.model_dump() for p in body.points], body.source)
    return {"matrix_m": matrix, "source": used, "path_stats": stats, "notice": notice}


@api.post("/geometry")
def geometry(body: schemas.GeometryIn):
    return {"line": road_data.route_geometry([p.model_dump() for p in body.stops], body.source)}


# ---------------------------------------------------------------- Benchmarks


@api.post("/benchmarks", response_model=schemas.BenchmarkOut, status_code=201)
def create_benchmark(session: Session = Db):
    if session.scalar(select(Benchmark).where(Benchmark.status == "running")):
        raise HTTPException(409, "A benchmark is already running.")
    benchmark = Benchmark(status="running", config=solver_process.BENCHMARK, progress={}, rows=[])
    session.add(benchmark)
    session.commit()
    runner.start_benchmark(benchmark.id)
    return benchmark


@api.get("/benchmarks/latest", response_model=schemas.BenchmarkOut | None)
def latest_benchmark(session: Session = Db):
    return session.scalar(select(Benchmark).order_by(Benchmark.id.desc()).limit(1))


@api.post("/benchmarks/{identifier}/cancel", response_model=schemas.BenchmarkOut)
def cancel_benchmark(identifier: int, session: Session = Db):
    benchmark = _get(session, Benchmark, identifier)
    if benchmark.status == "running":
        runner.cancel("benchmark", identifier)
    return benchmark


app.include_router(api)

# In production FastAPI also serves the built React app from one address.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(FRONTEND_DIST / "index.html")
