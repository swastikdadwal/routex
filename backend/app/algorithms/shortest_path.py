"""Road-network shortest paths: Dijkstra and A* on a directed graph."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6371000.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@dataclass
class RoadGraph:
    lat: list[float] = field(default_factory=list)
    lng: list[float] = field(default_factory=list)
    adjacency: list[list[tuple[int, float]]] = field(default_factory=list)

    def add_node(self, lat: float, lng: float) -> int:
        self.lat.append(lat)
        self.lng.append(lng)
        self.adjacency.append([])
        return len(self.lat) - 1

    def add_edge(self, a: int, b: int, oneway: bool = False) -> None:
        length = haversine(self.lat[a], self.lng[a], self.lat[b], self.lng[b])
        self.adjacency[a].append((b, length))
        if not oneway:
            self.adjacency[b].append((a, length))

    def __len__(self) -> int:
        return len(self.lat)


def dijkstra(graph: RoadGraph, source: int, targets: set[int] | None = None):
    """Returns (distance, previous, settled). Stops once all targets are settled."""
    distance = [math.inf] * len(graph)
    previous = [-1] * len(graph)
    distance[source] = 0.0
    heap = [(0.0, source)]
    settled = 0
    remaining = set(targets) if targets else None
    adjacency = graph.adjacency
    while heap:
        d, u = heapq.heappop(heap)
        if d > distance[u]:
            continue
        settled += 1
        if remaining is not None:
            remaining.discard(u)
            if not remaining:
                break
        for v, length in adjacency[u]:
            value = d + length
            if value < distance[v]:
                distance[v] = value
                previous[v] = u
                heapq.heappush(heap, (value, v))
    return distance, previous, settled


def astar(graph: RoadGraph, source: int, target: int):
    """Returns (distance, path, settled). Haversine is admissible and consistent
    here because every edge length is the haversine of its endpoints."""
    goal_lat, goal_lng = graph.lat[target], graph.lng[target]
    best = {source: 0.0}
    previous = {}
    start = haversine(graph.lat[source], graph.lng[source], goal_lat, goal_lng)
    heap = [(start, 0.0, source)]
    closed = set()
    adjacency, lat, lng = graph.adjacency, graph.lat, graph.lng
    while heap:
        _, d, u = heapq.heappop(heap)
        if u in closed:
            continue
        closed.add(u)
        if u == target:
            return d, _walk(previous, source, target), len(closed)
        for v, length in adjacency[u]:
            value = d + length
            if value < best.get(v, math.inf):
                best[v] = value
                previous[v] = u
                heapq.heappush(heap, (value + haversine(lat[v], lng[v], goal_lat, goal_lng), value, v))
    return math.inf, [], len(closed)


def _walk(previous, source: int, target: int) -> list[int]:
    path = [target]
    while path[-1] != source:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def path_from(previous: list[int], source: int, target: int) -> list[int]:
    if source == target:
        return [source]
    if previous[target] < 0:
        return []
    path = [target]
    while path[-1] != source:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def reachable(adjacency: list[list[tuple[int, float]]], start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        for v, _ in adjacency[stack.pop()]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def strongly_connected_core(graph: RoadGraph) -> set[int]:
    """The nodes that can both reach and be reached from a well-connected node.

    Snapping stops only to this set guarantees a route exists between any two
    stops, even where the map data has isolated roads or one-way dead ends.
    """
    reverse: list[list[tuple[int, float]]] = [[] for _ in range(len(graph))]
    for u, edges in enumerate(graph.adjacency):
        for v, length in edges:
            reverse[v].append((u, length))
    best: set[int] = set()
    unassigned = set(range(len(graph)))
    # Try the busiest junctions first; the main road network contains them.
    seeds = sorted(unassigned, key=lambda u: -len(graph.adjacency[u]))
    for seed in seeds[:25]:
        if seed not in unassigned:
            continue
        core = reachable(graph.adjacency, seed) & reachable(reverse, seed)
        unassigned -= core
        if len(core) > len(best):
            best = core
        if len(best) > len(graph) / 2:
            break
    return best


def nearest_node(graph: RoadGraph, candidates, lat: float, lng: float) -> int:
    # Squared equirectangular distance is enough to rank nearby nodes.
    scale = math.cos(math.radians(lat)) ** 2
    glat, glng = graph.lat, graph.lng
    return min(candidates, key=lambda u: (glat[u] - lat) ** 2 + scale * (glng[u] - lng) ** 2)
