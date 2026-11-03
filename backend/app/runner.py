"""Runs comparisons and benchmarks in the background, saving progress to the database."""
from __future__ import annotations

import logging
import multiprocessing
import queue as queue_module
import threading

from sqlalchemy import update

from . import road_data, solver_process
from .algorithms.solvers import Instance, assign_cheapest, lower_bound
from .db import SessionLocal
from .models import Benchmark, Run, RunResult

log = logging.getLogger("routex.runner")
_context = multiprocessing.get_context("spawn")
_lock = threading.Lock()
_active: dict[tuple[str, int], multiprocessing.Process] = {}
_cancelled: set[tuple[str, int]] = set()


def _consume(key, process, queue, on_message) -> bool:
    """Feeds worker messages to on_message. True if the worker finished cleanly."""
    with _lock:
        _active[key] = process
        if key in _cancelled:
            process.terminate()
    try:
        while True:
            try:
                message = queue.get(timeout=0.2)
            except queue_module.Empty:
                if process.is_alive():
                    continue
                try:  # the worker may have posted just before it exited
                    message = queue.get(timeout=0.5)
                except queue_module.Empty:
                    return False
            if message["type"] == "done":
                return True
            on_message(message)
    finally:
        process.join(timeout=5)
        with _lock:
            _active.pop(key, None)


def cancel(kind: str, identifier: int) -> None:
    key = (kind, identifier)
    with _lock:
        _cancelled.add(key)
        process = _active.get(key)
        if process:
            process.terminate()


def _was_cancelled(key) -> bool:
    with _lock:
        return key in _cancelled


def _set_run(run_id: int, **values) -> None:
    with SessionLocal() as session:
        session.execute(update(Run).where(Run.id == run_id).values(**values))
        session.commit()


def _result_row(run_id: int, algorithm: str, result: dict, scenario: dict) -> RunResult:
    vehicles = scenario["vehicles"]
    orders = scenario["orders"]
    planned = sorted(
        ((route, metres) for route, metres in zip(result["routes"], result["route_distances"]) if route),
        key=lambda item: min(item[0]),
    )
    loads = [sum(orders[stop - 1]["demand"] for stop in route) for route, _ in planned]
    assignment = assign_cheapest(
        loads,
        [metres for _, metres in planned],
        [v["capacity"] for v in vehicles],
        [v["cost_per_km"] for v in vehicles],
    )
    routes = []
    total_cost = 0.0
    for (route, metres), load, index in zip(planned, loads, assignment):
        cost = metres / 1000 * vehicles[index]["cost_per_km"]
        total_cost += cost
        routes.append({"vehicle_index": index, "stops": route, "distance_m": metres, "load": load, "cost": cost})
    routes.sort(key=lambda route: route["vehicle_index"])
    if result["skipped"]:
        status, detail = "skipped", result["skipped"]
    elif result["infeasible"]:
        status, detail = "infeasible", None
    elif result["timed_out"] and result["unserved"]:
        status, detail = "time_limit", "No complete plan before the limit"
    elif result["unserved"]:
        status, detail = "incomplete", None
    elif result["timed_out"]:
        status, detail = "time_limit", None
    elif result["optimal"]:
        status, detail = "optimal", None
    else:
        status, detail = "heuristic", None
    complete = status in ("optimal", "heuristic") or (status == "time_limit" and not result["unserved"])
    return RunResult(
        run_id=run_id,
        algorithm=algorithm,
        status=status,
        detail=detail,
        distance_m=result["distance"] if complete else None,
        cost=total_cost if complete else None,
        elapsed_ms=None if result["skipped"] else result["elapsed_ms"],
        work=None if result["skipped"] else min(result["work"], 2**31 - 1),
        routes=routes,
        unserved=result["unserved"],
    )


def _execute_run(run_id: int) -> None:
    key = ("run", run_id)
    try:
        with SessionLocal() as session:
            run = session.get(Run, run_id)
            scenario = run.scenario
            algorithms = run.algorithms
            source = run.requested_source
            time_limit_s = run.time_limit_s

        points = [scenario["warehouse"], *scenario["orders"]]
        _set_run(run_id, status="distances")
        matrix, used, stats, notice = road_data.distance_matrix(points, source)
        instance = Instance(
            matrix,
            [0, *[o["demand"] for o in scenario["orders"]]],
            [v["capacity"] for v in scenario["vehicles"]],
        )
        _set_run(
            run_id,
            status="solving",
            distance_source=used,
            path_stats=stats,
            notice=notice,
            lower_bound_m=lower_bound(instance),
        )
        if _was_cancelled(key):
            _set_run(run_id, status="cancelled")
            return

        queue = _context.Queue()
        process = _context.Process(
            target=solver_process.run_solvers,
            args=(
                {"dist": matrix, "demand": instance.demand, "capacities": instance.capacities},
                algorithms,
                time_limit_s,
                queue,
            ),
            daemon=True,
        )
        process.start()

        def on_message(message):
            with SessionLocal() as session:
                session.add(_result_row(run_id, message["algorithm"], message["result"], scenario))
                session.commit()

        finished = _consume(key, process, queue, on_message)
        if _was_cancelled(key):
            _set_run(run_id, status="cancelled")
        elif finished:
            _set_run(run_id, status="done")
        else:
            _set_run(run_id, status="failed", notice="The solver process stopped unexpectedly.")
    except Exception:
        log.exception("Run %s failed", run_id)
        _set_run(run_id, status="failed", notice="The run failed. See the server log for details.")
    finally:
        with _lock:
            _cancelled.discard(key)


def start_run(run_id: int) -> None:
    threading.Thread(target=_execute_run, args=(run_id,), daemon=True).start()


def _set_benchmark(benchmark_id: int, **values) -> None:
    with SessionLocal() as session:
        session.execute(update(Benchmark).where(Benchmark.id == benchmark_id).values(**values))
        session.commit()


def _execute_benchmark(benchmark_id: int) -> None:
    key = ("benchmark", benchmark_id)
    try:
        queue = _context.Queue()
        process = _context.Process(target=solver_process.run_benchmark, args=(queue,), daemon=True)
        process.start()

        def on_message(message):
            if message["type"] == "progress":
                _set_benchmark(
                    benchmark_id,
                    progress={"done": message["done"], "total": message["total"], "n": message["n"]},
                )
            elif message["type"] == "rows":
                _set_benchmark(benchmark_id, rows=message["rows"])

        finished = _consume(key, process, queue, on_message)
        if _was_cancelled(key):
            _set_benchmark(benchmark_id, status="cancelled")
        else:
            _set_benchmark(benchmark_id, status="done" if finished else "failed")
    except Exception:
        log.exception("Benchmark %s failed", benchmark_id)
        _set_benchmark(benchmark_id, status="failed")
    finally:
        with _lock:
            _cancelled.discard(key)


def start_benchmark(benchmark_id: int) -> None:
    threading.Thread(target=_execute_benchmark, args=(benchmark_id,), daemon=True).start()


def mark_interrupted() -> None:
    """Anything still 'running' at startup died with the previous server."""
    with SessionLocal() as session:
        session.execute(
            update(Run)
            .where(Run.status.in_(("pending", "distances", "solving")))
            .values(status="failed", notice="The server restarted during this run.")
        )
        session.execute(update(Benchmark).where(Benchmark.status == "running").values(status="failed"))
        session.commit()
