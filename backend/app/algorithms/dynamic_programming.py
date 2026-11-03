"""Dynamic programming: Held-Karp TSP for each subset, then the best partition across vehicles."""
from .common import INF, Budget, Instance, Result, finish

DP_MAX_ORDERS = 13


def dynamic_programming(inst: Instance, budget: Budget) -> Result:
    n, dist, demand, capacities = inst.n, inst.dist, inst.demand, inst.capacities
    if n > DP_MAX_ORDERS:
        return Result(skipped=f"Over {DP_MAX_ORDERS} orders")
    if n == 0:
        return finish(inst, [], optimal=True)
    size = 1 << n
    largest = capacities[0] if capacities else 0
    work = 0

    load = [0] * size
    for s in range(1, size):
        low = s & -s
        load[s] = load[s ^ low] + demand[low.bit_length()]

    # Step 1, Held-Karp: shortest path from the warehouse through subset s,
    # ending at j. Subsets no vehicle could carry are never built.
    path = [INF] * (size * n)
    parent = [-1] * (size * n)
    for j in range(n):
        if demand[j + 1] <= largest:
            path[(1 << j) * n + j] = dist[0][j + 1]
    for s in range(1, size):
        if load[s] > largest:
            continue
        if s & 1023 == 0 and budget.expired():
            return Result(timed_out=True, work=work)
        for j in range(n):
            cost = path[s * n + j]
            if cost == INF:
                continue
            row = dist[j + 1]
            for k in range(n):
                bit = 1 << k
                if s & bit:
                    continue
                grown = s | bit
                if load[grown] > largest:
                    continue
                work += 1
                value = cost + row[k + 1]
                if value < path[grown * n + k]:
                    path[grown * n + k] = value
                    parent[grown * n + k] = j

    # tour[s]: the best closed route serving exactly s with one vehicle.
    tour = [INF] * size
    tour_last = [-1] * size
    tour[0] = 0.0
    for s in range(1, size):
        if load[s] > largest:
            continue
        for j in range(n):
            value = path[s * n + j] + dist[j + 1][0]
            if value < tour[s]:
                tour[s] = value
                tour_last[s] = j

    # Step 2, partition: best[s] after k vehicles is the cheapest way to serve
    # s. Capacities differ, so every non-empty subset of s must be tried.
    best = [INF] * size
    best[0] = 0.0
    choices = []
    for capacity in capacities:
        following = best[:]
        choice = [0] * size
        for s in range(1, size):
            if s & 1023 == 0 and budget.expired():
                return Result(timed_out=True, work=work)
            top = following[s]
            pick = 0
            t = s
            while t:
                work += 1
                if load[t] <= capacity:
                    value = tour[t] + best[s ^ t]
                    if value < top:
                        top = value
                        pick = t
                t = (t - 1) & s
            following[s] = top
            choice[s] = pick
        choices.append(choice)
        best = following

    full = size - 1
    if best[full] == INF:
        return finish(inst, [], work=work, optimal=True, infeasible=True)

    routes = [[] for _ in capacities]
    s = full
    for k in range(len(capacities) - 1, -1, -1):
        subset = choices[k][s]
        if subset == 0:
            continue
        route = []
        walk, j = subset, tour_last[subset]
        while j >= 0:
            route.append(j + 1)
            previous = parent[walk * n + j]
            walk ^= 1 << j
            j = previous
        routes[k] = route[::-1]
        s ^= subset
    return finish(inst, routes, work=work, optimal=True)
