"""Approximation: a double-tree tour from a minimum spanning tree, split by capacity."""
from .common import INF, Budget, Instance, Result, finish, spanning_tree


def _split_tour(sequence, dist, demand, capacities, counter):
    """Cheapest cut of a fixed sequence into consecutive vehicles, or None."""
    n = len(sequence)
    along = [0.0] * n
    for i in range(1, n):
        along[i] = along[i - 1] + dist[sequence[i - 1]][sequence[i]]

    previous = [INF] * (n + 1)
    previous[0] = 0.0
    cuts = []
    for capacity in capacities:
        current = previous[:]  # keeping i unchanged leaves this vehicle empty
        cut = list(range(n + 1))
        for i in range(1, n + 1):
            load = 0
            for j in range(i - 1, -1, -1):
                load += demand[sequence[j]]
                if load > capacity:
                    break
                counter[0] += 1
                if previous[j] == INF:
                    continue
                value = (
                    previous[j]
                    + dist[0][sequence[j]]
                    + along[i - 1]
                    - along[j]
                    + dist[sequence[i - 1]][0]
                )
                if value < current[i]:
                    current[i] = value
                    cut[i] = j
        cuts.append(cut)
        previous = current
    if previous[n] == INF:
        return None

    routes = [[] for _ in capacities]
    end = n
    for k in range(len(capacities) - 1, -1, -1):
        start = cuts[k][end]
        routes[k] = sequence[start:end]
        end = start
    return previous[n], routes


def approximation(inst: Instance, budget: Budget | None = None) -> Result:
    n, dist, demand, capacities = inst.n, inst.dist, inst.demand, inst.capacities
    if n == 0:
        return finish(inst, [])
    parent, _ = spanning_tree(dist)
    children = [[] for _ in range(n + 1)]
    for v in range(1, n + 1):
        children[parent[v]].append(v)
    for v in range(n + 1):
        children[v].sort(key=lambda c, v=v: -dist[v][c])

    # A preorder walk shortcuts the doubled MST. With the triangle inequality
    # this tour is at most 2 x MST, and MST <= the optimal tour.
    tour = []
    stack = [0]
    while stack:
        v = stack.pop()
        if v:
            tour.append(v)
        stack.extend(children[v])

    counter = [0]
    best = None
    for rotation in range(n):
        split = _split_tour(tour[rotation:] + tour[:rotation], dist, demand, capacities, counter)
        if split and (best is None or split[0] < best[0]):
            best = split
    if best:
        return finish(inst, best[1], work=counter[0])

    # No consecutive cut fits the fleet: fill first-fit in tour order, so the
    # plan stays usable and any order that does not fit is reported unserved.
    routes = [[] for _ in capacities]
    loads = [0] * len(capacities)
    for order in tour:
        for k, capacity in enumerate(capacities):
            if loads[k] + demand[order] <= capacity:
                routes[k].append(order)
                loads[k] += demand[order]
                break
    return finish(inst, routes, work=counter[0])
