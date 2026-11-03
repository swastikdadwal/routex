"""Solvers for the capacitated vehicle routing problem (CVRP).

Each technique has its own module. This one lists them, runs them through
`solve`, and holds the lower bound and vehicle assignment used on their results.

Solvers receive vehicles sorted by descending capacity. `solve` handles the
sorting and maps the routes back to the caller's vehicle order.
"""
import time
from functools import lru_cache
from itertools import groupby

from .approximation import approximation
from .branch_bound import branch_and_bound
from .brute_force import BRUTE_FORCE_MAX_PLANS, brute_force, brute_force_plan_count
from .common import EPS, INF, Budget, Instance, Result, route_length, spanning_tree
from .dynamic_programming import DP_MAX_ORDERS, dynamic_programming
from .greedy import greedy

ALGORITHMS = [
    {
        "id": "greedy",
        "name": "Greedy",
        "method": "Nearest neighbour, one vehicle at a time",
        "complexity": "O(n²)",
        "work_unit": "comparisons",
    },
    {
        "id": "dp",
        "name": "Dynamic Programming",
        "method": "Held–Karp TSP plus subset partitioning",
        "complexity": "O(2ⁿn² + m·3ⁿ)",
        "work_unit": "transitions",
    },
    {
        "id": "brute",
        "name": "Brute Force",
        "method": "Every order sequence and vehicle split",
        "complexity": "O(n!·C(n+m−1, m−1))",
        "work_unit": "nodes",
    },
    {
        "id": "bnb",
        "name": "Branch and Bound",
        "method": "Depth-first search with an MST lower bound",
        "complexity": "O(n!) worst case",
        "work_unit": "nodes",
    },
    {
        "id": "approx",
        "name": "Approximation",
        "method": "MST double-tree tour, split by capacity",
        "complexity": "O(m·n³)",
        "work_unit": "operations",
    },
]
ALGORITHM_IDS = [a["id"] for a in ALGORITHMS]
# Fastest first, so stopping a long exact search keeps the quick results.
EXECUTION_ORDER = ["greedy", "approx", "dp", "bnb", "brute"]


# -------------------------------------------------------------- Lower bound


def lower_bound(inst: Instance) -> float:
    """A distance no plan can beat, for instances too big for exact solvers.

    The MST bound always holds: any plan connects the warehouse and every order.
    The radial bound needs the triangle inequality, so it is only used when the
    matrix satisfies it.
    """
    dist, size = inst.dist, len(inst.dist)
    if size <= 1 or not inst.capacities:
        return 0.0
    _, mst = spanning_tree(dist)
    for a in range(size):
        for b in range(size):
            for c in range(size):
                if dist[a][c] > dist[a][b] + dist[b][c] + 1e-6:
                    return mst
    largest = max(inst.capacities)
    radial = sum(2 * dist[0][i] * inst.demand[i] / largest for i in range(1, size))
    return max(mst, radial)


# -------------------------------------------------------- Vehicle assignment


def assign_cheapest(loads: list[int], distances: list[float], capacities: list[int], rates: list[float]) -> list[int]:
    """The vehicle for each route that minimises total cost within capacity.

    Distance stays fixed, so this lowers cost without changing a plan's routes.
    A dynamic program over the set of used vehicles: O(r·m·2^m) for r routes.
    Ties go to the lowest vehicle numbers, so equal plans get equal assignments.
    """
    routes, vehicles = len(loads), len(capacities)

    @lru_cache(maxsize=None)
    def best(route: int, used: int) -> tuple[float, tuple[int, ...]]:
        if route == routes:
            return 0.0, ()
        answer = (INF, ())
        for vehicle in range(vehicles):
            if used & (1 << vehicle) or loads[route] > capacities[vehicle]:
                continue
            cost, rest = best(route + 1, used | (1 << vehicle))
            total = cost + distances[route] * rates[vehicle]
            if total < answer[0] - EPS:
                answer = (total, (vehicle, *rest))
        return answer

    return list(best(0, 0)[1])


# ------------------------------------------------------------------ Dispatch

_SOLVERS = {
    "greedy": greedy,
    "dp": dynamic_programming,
    "brute": brute_force,
    "bnb": branch_and_bound,
    "approx": approximation,
}


def solve(algorithm: str, inst: Instance, time_limit_s: float = 10.0) -> Result:
    """Runs one solver and returns routes indexed by the caller's vehicle order."""
    order = sorted(range(inst.m), key=lambda k: -inst.capacities[k])
    ordered = Instance(inst.dist, inst.demand, [inst.capacities[k] for k in order])

    started = time.perf_counter()
    result = _SOLVERS[algorithm](ordered, Budget(time_limit_s))
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    if not result.routes:  # skipped, or timed out before building any plan
        result.routes = [[] for _ in range(inst.m)]
        result.route_distances = [0.0] * inst.m
        if not result.skipped:
            result.unserved = list(range(1, inst.n + 1))
        return result

    # Within a capacity group the vehicles are interchangeable. A stable order
    # gives identical plans identical vehicle numbers, whichever solver found them.
    pairs = list(zip(result.routes, result.route_distances))
    arranged: list = []
    for _, group in groupby(range(inst.m), key=lambda k: ordered.capacities[k]):
        members = [pairs[k] for k in group]
        members.sort(key=lambda p: (not p[0], min(p[0]) if p[0] else 0))
        arranged.extend(members)

    routes = [[] for _ in range(inst.m)]
    distances = [0.0] * inst.m
    for position, vehicle in enumerate(order):
        routes[vehicle], distances[vehicle] = arranged[position]
    result.routes, result.route_distances = routes, distances
    return result
