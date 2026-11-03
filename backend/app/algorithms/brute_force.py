"""Brute force: every order sequence and vehicle split, with no pruning on cost."""
import math

from .common import EPS, INF, Budget, Instance, Result, finish

BRUTE_FORCE_MAX_PLANS = 3_000_000


def brute_force_plan_count(n: int, m: int) -> int:
    """Order sequences times the ways to cut each sequence across m vehicles."""
    if m == 0:
        return 0
    return math.factorial(n) * math.comb(n + m - 1, m - 1)


def brute_force(inst: Instance, budget: Budget) -> Result:
    n, dist, demand, capacities = inst.n, inst.dist, inst.demand, inst.capacities
    m = inst.m
    plans = brute_force_plan_count(n, m)
    if plans > BRUTE_FORCE_MAX_PLANS:
        return Result(skipped=f"{plans:,} plans to check")
    if n == 0:
        return finish(inst, [], optimal=True)

    used = [False] * (n + 1)
    routes: list[list[int]] = [[] for _ in range(m)]
    best = INF
    best_routes = None
    nodes = 0
    timed_out = False

    # No pruning on cost, deliberately: every feasible plan is evaluated.
    def visit(vehicle: int, current: int, load: int, cost: float, remaining: int) -> None:
        nonlocal best, best_routes, nodes, timed_out
        nodes += 1
        if nodes & 8191 == 0 and budget.expired():
            timed_out = True
        if timed_out:
            return
        if remaining == 0:
            total = cost + dist[current][0]
            if total < best - EPS:
                best = total
                best_routes = [r[:] for r in routes]
            return
        capacity = capacities[vehicle]
        row = dist[current]
        for u in range(1, n + 1):
            if used[u] or load + demand[u] > capacity:
                continue
            used[u] = True
            routes[vehicle].append(u)
            visit(vehicle, u, load + demand[u], cost + row[u], remaining - 1)
            routes[vehicle].pop()
            used[u] = False
        if vehicle + 1 < m:
            visit(vehicle + 1, 0, 0, cost + row[0], remaining)

    if m > 0:
        visit(0, 0, 0, 0.0, n)
    proven = not timed_out
    return finish(
        inst,
        best_routes or [],
        work=nodes,
        timed_out=timed_out,
        optimal=proven,
        infeasible=proven and best_routes is None,
    )
