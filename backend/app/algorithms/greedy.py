"""Greedy: nearest neighbour, filling one vehicle at a time."""
from .common import INF, Budget, Instance, Result, finish


def greedy(inst: Instance, budget: Budget | None = None) -> Result:
    dist, demand = inst.dist, inst.demand
    left = set(range(1, inst.n + 1))
    routes = []
    work = 0
    for capacity in inst.capacities:
        route: list[int] = []
        current, load = 0, 0
        while True:
            nearest, best = -1, INF
            for u in left:
                work += 1
                if load + demand[u] <= capacity and dist[current][u] < best:
                    best = dist[current][u]
                    nearest = u
            if nearest < 0:
                break
            route.append(nearest)
            left.remove(nearest)
            load += demand[nearest]
            current = nearest
        routes.append(route)
    return finish(inst, routes, work=work)
