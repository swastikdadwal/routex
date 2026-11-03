"""Branch and bound: depth-first search pruned with a minimum spanning tree bound."""
from .common import EPS, INF, Budget, Instance, Result, finish
from .greedy import greedy
from .approximation import approximation


def branch_and_bound(inst: Instance, budget: Budget) -> Result:
    n, dist, demand, capacities = inst.n, inst.dist, inst.demand, inst.capacities
    m = inst.m
    if n == 0:
        return finish(inst, [], optimal=True)

    # Start from the better fast heuristic so pruning bites straight away.
    best = INF
    best_routes = None
    for start in (greedy(inst), approximation(inst)):
        if not start.unserved and start.distance < best:
            best = start.distance
            best_routes = [r[:] for r in start.routes]

    neighbours = [
        sorted((j for j in range(1, n + 1) if j != i), key=lambda j, i=i: dist[i][j])
        for i in range(n + 1)
    ]
    # Same-capacity vehicles are interchangeable; next_group skips that symmetry.
    next_group = [m] * m
    for k in range(m - 2, -1, -1):
        next_group[k] = next_group[k + 1] if capacities[k] == capacities[k + 1] else k + 1
    capacity_from = [0] * (m + 1)
    for k in range(m - 1, -1, -1):
        capacity_from[k] = capacity_from[k + 1] + capacities[k]

    visited = [False] * (n + 1)
    routes: list[list[int]] = [[] for _ in range(m)]
    nodes = 0
    pruned = 0
    timed_out = False

    def spanning_bound(current: int) -> float:
        # What remains must connect the current stop, the warehouse and every
        # open order, so it costs at least the MST over exactly those nodes.
        active = [i for i in range(1, n + 1) if not visited[i] or i == current]
        key = [dist[0][i] for i in active]
        total = 0.0
        while active:
            pick = min(range(len(active)), key=key.__getitem__)
            total += key[pick]
            node = active[pick]
            active[pick] = active[-1]
            key[pick] = key[-1]
            active.pop()
            key.pop()
            row = dist[node]
            for i, other in enumerate(active):
                if row[other] < key[i]:
                    key[i] = row[other]
        return total

    # Symmetry breaking keeps one copy of each equivalent plan:
    #   a route's first order has a lower number than its last (direction), and
    #   within a capacity group, routes rise by first order with empties last.
    def search(vehicle, current, load, cost, first, floor, demand_left, count_left):
        nonlocal best, best_routes, nodes, pruned, timed_out
        nodes += 1
        if nodes & 1023 == 0 and budget.expired():
            timed_out = True
        if timed_out:
            return

        if count_left == 0:
            if current != 0 and first > current:
                pruned += 1
                return
            total = cost + dist[current][0]
            if total < best - EPS:
                best = total
                best_routes = [r[:] for r in routes]
            return

        room = capacities[vehicle] - load + capacity_from[vehicle + 1]
        if demand_left > room or cost + spanning_bound(current) >= best - EPS:
            pruned += 1
            return

        if current == 0:
            capacity = capacities[vehicle]
            for u in neighbours[0]:
                if visited[u] or u <= floor or demand[u] > capacity:
                    continue
                visited[u] = True
                routes[vehicle].append(u)
                search(vehicle, u, demand[u], cost + dist[0][u], u, floor, demand_left - demand[u], count_left - 1)
                routes[vehicle].pop()
                visited[u] = False
            # Leaving this vehicle empty also empties its whole capacity group.
            target = next_group[vehicle]
            if target < m:
                search(target, 0, 0, cost, 0, 0, demand_left, count_left)
            return

        capacity = capacities[vehicle]
        for u in neighbours[current]:
            if visited[u] or load + demand[u] > capacity:
                continue
            visited[u] = True
            routes[vehicle].append(u)
            search(vehicle, u, load + demand[u], cost + dist[current][u], first, floor, demand_left - demand[u], count_left - 1)
            routes[vehicle].pop()
            visited[u] = False
        if vehicle + 1 < m and first <= current:
            same_group = capacities[vehicle + 1] == capacities[vehicle]
            search(vehicle + 1, 0, 0, cost + dist[current][0], 0, first if same_group else 0, demand_left, count_left)

    if m > 0:
        search(0, 0, 0, 0.0, 0, 0, sum(demand), n)
    proven = not timed_out
    return finish(
        inst,
        best_routes or [],
        work=nodes,
        timed_out=timed_out,
        optimal=proven,
        infeasible=proven and best_routes is None,
    )
