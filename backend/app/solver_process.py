"""Entry points for the child process that runs solvers.

A separate process keeps timings clean, keeps the API responsive during long
searches, and lets Stop end any solver immediately. This module must import only
the algorithms, because Windows re-imports it in every new process.
"""
import math
import random

from .algorithms.solvers import ALGORITHM_IDS, DP_MAX_ORDERS, EXECUTION_ORDER, Instance, solve

BENCHMARK = {
    "sizes": list(range(5, 21)),
    "trials": 5,
    "vehicles": 3,
    "time_limit_s": 2.0,
    "seed": 2026,
}


def run_solvers(instance: dict, algorithms: list[str], time_limit_s: float, queue) -> None:
    inst = Instance(instance["dist"], instance["demand"], instance["capacities"])
    for algorithm in EXECUTION_ORDER:
        if algorithm in algorithms:
            result = solve(algorithm, inst, time_limit_s)
            queue.put({"type": "result", "algorithm": algorithm, "result": result.__dict__})
    queue.put({"type": "done"})


def _random_instance(rng: random.Random, n: int, vehicles: int) -> Instance:
    points = [(5000.0, 5000.0)] + [(rng.random() * 10000, rng.random() * 10000) for _ in range(n)]
    dist = [[math.dist(a, b) for b in points] for a in points]
    demand = [0] + [rng.randint(1, 3) for _ in range(n)]
    base = max(3, math.ceil(sum(demand) * 1.4 / vehicles))
    # A mixed fleet, as in the app: one vehicle above average and one below.
    capacities = [base + 1, base, max(3, base - 1)][:vehicles]
    return Instance(dist, demand, capacities)


def run_benchmark(queue) -> None:
    config = BENCHMARK
    rng = random.Random(config["seed"])
    rows = []
    trials = config["trials"]
    total = len(config["sizes"]) * trials
    done = 0
    for n in config["sizes"]:
        stats = {
            a: {"ms": 0.0, "runs": 0, "gap": 0.0, "gap_runs": 0, "incomplete": 0, "timed_out": 0, "skipped": 0}
            for a in ALGORITHM_IDS
        }
        for _ in range(trials):
            inst = _random_instance(rng, n, config["vehicles"])
            results = {a: solve(a, inst, config["time_limit_s"]) for a in EXECUTION_ORDER}
            # Above DP's limit only some Branch and Bound trials finish, and averaging
            # the gap over those alone would not be comparable, so it is left out.
            proven = [r.distance for r in results.values() if r.optimal and not r.infeasible]
            optimum = min(proven) if proven and n <= DP_MAX_ORDERS else None
            for algorithm, result in results.items():
                entry = stats[algorithm]
                if result.skipped:
                    entry["skipped"] += 1
                    continue
                entry["ms"] += result.elapsed_ms
                entry["runs"] += 1
                if result.timed_out:
                    entry["timed_out"] += 1
                if result.unserved:
                    entry["incomplete"] += 1
                elif optimum:
                    entry["gap"] += (result.distance - optimum) / optimum * 100
                    entry["gap_runs"] += 1
            done += 1
            queue.put({"type": "progress", "done": done, "total": total, "n": n})
        row = {"n": n, "algorithms": {}}
        for algorithm, entry in stats.items():
            row["algorithms"][algorithm] = {
                "ms": entry["ms"] / entry["runs"] if entry["runs"] else None,
                "gap": entry["gap"] / entry["gap_runs"] if entry["gap_runs"] else None,
                "incomplete": entry["incomplete"],
                "timed_out": entry["timed_out"],
                "skipped": entry["skipped"],
            }
        rows.append(row)
        queue.put({"type": "rows", "rows": rows})
    queue.put({"type": "done"})
