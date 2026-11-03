"""What every solver shares: the problem, the result, and small helpers.

Node 0 of the distance matrix is the warehouse and nodes 1..n are orders. Each
vehicle has its own capacity and may stay unused. Every solver minimises the
total distance driven, warehouse to warehouse.
"""
import math
import time
from dataclasses import dataclass, field

INF = math.inf
EPS = 1e-9


@dataclass(frozen=True)
class Instance:
    dist: list[list[float]]
    demand: list[int]
    capacities: list[int]

    @property
    def n(self) -> int:
        return len(self.dist) - 1

    @property
    def m(self) -> int:
        return len(self.capacities)


@dataclass
class Result:
    routes: list[list[int]] = field(default_factory=list)  # one per vehicle
    distance: float = 0.0
    route_distances: list[float] = field(default_factory=list)
    unserved: list[int] = field(default_factory=list)
    work: int = 0
    optimal: bool = False
    timed_out: bool = False
    infeasible: bool = False
    skipped: str | None = None
    elapsed_ms: float = 0.0


class Budget:
    def __init__(self, seconds: float):
        self.deadline = time.perf_counter() + seconds

    def expired(self) -> bool:
        return time.perf_counter() > self.deadline


def route_length(dist: list[list[float]], route: list[int]) -> float:
    if not route:
        return 0.0
    total = dist[0][route[0]] + dist[route[-1]][0]
    for a, b in zip(route, route[1:]):
        total += dist[a][b]
    return total


def finish(inst: Instance, routes: list[list[int]], **extra) -> Result:
    padded = [list(r) for r in routes] + [[] for _ in range(inst.m - len(routes))]
    served = {order for route in padded for order in route}
    distances = [route_length(inst.dist, route) for route in padded]
    return Result(
        routes=padded,
        route_distances=distances,
        distance=sum(distances),
        unserved=[i for i in range(1, inst.n + 1) if i not in served],
        **extra,
    )


def spanning_tree(dist: list[list[float]]) -> tuple[list[int], float]:
    size = len(dist)
    parent = [-1] * size
    key = [INF] * size
    done = [False] * size
    key[0] = 0.0
    weight = 0.0
    for _ in range(size):
        u = min((i for i in range(size) if not done[i]), key=key.__getitem__)
        done[u] = True
        weight += key[u]
        for v in range(size):
            if not done[v] and dist[u][v] < key[v]:
                key[v] = dist[u][v]
                parent[v] = u
    return parent, weight
