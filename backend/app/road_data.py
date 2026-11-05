"""Distance matrices and road geometry from OSRM, or from Dijkstra on OSM roads."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import httpx

from .algorithms.shortest_path import (
    RoadGraph,
    astar,
    dijkstra,
    haversine,
    nearest_node,
    path_from,
    strongly_connected_core,
)
from .config import settings

USER_AGENT = "RouteX/1.0 (student delivery optimisation project)"
DRIVABLE = (
    "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|"
    "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
)
BBOX_PADDING_DEGREES = 0.01
# The public road servers are often busy, and one answer takes 20-45 s when healthy.
OVERPASS_ROUNDS = 2
OVERPASS_ROUND_WAIT_S = 5
OVERPASS_ATTEMPT_TIMEOUT_S = 100
OVERPASS_TOTAL_BUDGET_S = 240


class RoadDataError(Exception):
    pass


def straight_matrix(points: list[dict]) -> list[list[float]]:
    return [[haversine(a["lat"], a["lng"], b["lat"], b["lng"]) for b in points] for a in points]


# --------------------------------------------------------------------- OSRM


def _coordinates(points: list[dict]) -> str:
    return ";".join(f"{p['lng']:.6f},{p['lat']:.6f}" for p in points)


def _osrm_get(path: str) -> dict:
    try:
        response = httpx.get(
            f"{settings.osrm_url}{path}", headers={"User-Agent": USER_AGENT}, timeout=30
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RoadDataError(f"OSRM request failed: {error}") from error
    if body.get("code") != "Ok":
        raise RoadDataError(f"OSRM answered {body.get('code')}")
    return body


def osrm_matrix(points: list[dict]) -> list[list[float]]:
    # One-way streets make distances direction-dependent. The solvers need a
    # symmetric matrix, so each pair uses the mean of its two directions.
    raw = _osrm_get(f"/table/v1/driving/{_coordinates(points)}?annotations=distance")["distances"]
    size = len(raw)
    if any(raw[i][j] is None for i in range(size) for j in range(size)):
        raise RoadDataError("OSRM found no road between two stops")
    return [[(raw[i][j] + raw[j][i]) / 2 for j in range(size)] for i in range(size)]


def osrm_geometry(points: list[dict]) -> list[list[float]]:
    body = _osrm_get(f"/route/v1/driving/{_coordinates(points)}?overview=full&geometries=geojson")
    return [[lat, lng] for lng, lat in body["routes"][0]["geometry"]["coordinates"]]


# ---------------------------------------------------- OSM graph and Dijkstra


@dataclass
class LoadedGraph:
    bbox: tuple[float, float, float, float]  # south, west, north, east
    graph: RoadGraph
    core: list[int]


_graph_lock = threading.Lock()
_graph_cache: list[LoadedGraph] = []
_GRAPH_CACHE_SIZE = 2


def _bbox(points: list[dict]) -> tuple[float, float, float, float]:
    lats = [p["lat"] for p in points]
    lngs = [p["lng"] for p in points]
    pad = BBOX_PADDING_DEGREES
    return (min(lats) - pad, min(lngs) - pad, max(lats) + pad, max(lngs) + pad)


def _covers(outer, inner) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def parse_overpass(elements: list[dict]) -> RoadGraph:
    graph = RoadGraph()
    index: dict[int, int] = {}
    for way in elements:
        if way.get("type") != "way" or "geometry" not in way:
            continue
        tags = way.get("tags", {})
        oneway_tag = tags.get("oneway", "")
        implied = tags.get("junction") in ("roundabout", "circular") or tags.get("highway") in (
            "motorway",
            "motorway_link",
        )
        reverse = oneway_tag == "-1"
        oneway = reverse or oneway_tag in ("yes", "true", "1") or (implied and oneway_tag != "no")
        nodes = []
        for node_id, position in zip(way["nodes"], way["geometry"]):
            if position is None:  # outside the query's bounding box
                nodes.append(None)
                continue
            if node_id not in index:
                index[node_id] = graph.add_node(position["lat"], position["lon"])
            nodes.append(index[node_id])
        for a, b in zip(nodes, nodes[1:]):
            if a is None or b is None or a == b:
                continue
            if reverse:
                graph.add_edge(b, a, oneway=True)
            else:
                graph.add_edge(a, b, oneway=oneway)
    return graph


def _download_roads(query: str) -> list[dict]:
    """Tries each road server in turn, for a limited number of rounds and total time."""
    servers = [settings.overpass_url, *settings.overpass_backup_urls]
    deadline = time.monotonic() + OVERPASS_TOTAL_BUDGET_S
    problem = "no server was tried"
    for round_number in range(OVERPASS_ROUNDS):
        if round_number:
            time.sleep(OVERPASS_ROUND_WAIT_S)
        for url in servers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RoadDataError(f"OpenStreetMap road servers did not answer in time ({problem})")
            try:
                response = httpx.post(
                    url,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=httpx.Timeout(min(remaining, OVERPASS_ATTEMPT_TIMEOUT_S), connect=10),
                )
                status = response.status_code
                if status == 429 or status >= 500:
                    problem = f"last answer: HTTP {status}"
                    continue
                if status >= 400:  # The request itself is wrong, so another server won't help.
                    raise RoadDataError(f"OpenStreetMap road download was refused (HTTP {status})")
                body = response.json()
            except httpx.TimeoutException:
                problem = "last attempt timed out"
                continue
            except (httpx.HTTPError, ValueError) as error:
                problem = f"last problem: {type(error).__name__}"
                continue
            elements = body.get("elements", [])
            if not elements and body.get("remark"):  # Busy servers give up with a remark.
                problem = "last server was too busy"
                continue
            return elements
    raise RoadDataError(f"OpenStreetMap road servers are busy ({problem})")


def load_graph(points: list[dict]) -> LoadedGraph:
    wanted = _bbox(points)
    with _graph_lock:
        for loaded in _graph_cache:
            if _covers(loaded.bbox, wanted):
                return loaded
        south, west, north, east = wanted
        query = (
            f'[out:json][timeout:120];way["highway"~"^({DRIVABLE})$"]'
            f"({south:.5f},{west:.5f},{north:.5f},{east:.5f});out body geom;"
        )
        graph = parse_overpass(_download_roads(query))
        core = strongly_connected_core(graph) if len(graph) else set()
        if not core:
            raise RoadDataError("OpenStreetMap returned no connected roads for this area")
        loaded = LoadedGraph(wanted, graph, list(core))
        _graph_cache.insert(0, loaded)
        del _graph_cache[_GRAPH_CACHE_SIZE:]
        return loaded


def dijkstra_matrix(points: list[dict]) -> tuple[list[list[float]], dict]:
    """Road distances between stops, with statistics comparing Dijkstra and A*."""
    loaded = load_graph(points)
    graph = loaded.graph
    snapped = [nearest_node(graph, loaded.core, p["lat"], p["lng"]) for p in points]
    size = len(points)
    raw = [[0.0] * size for _ in range(size)]

    started = time.perf_counter()
    dijkstra_settled = 0
    for i, source in enumerate(snapped):
        distance, _, settled = dijkstra(graph, source, set(snapped))
        dijkstra_settled += settled
        for j, target in enumerate(snapped):
            raw[i][j] = distance[target]
    dijkstra_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    astar_settled = 0
    for i, source in enumerate(snapped):
        for j, target in enumerate(snapped):
            if i != j:
                astar_settled += astar(graph, source, target)[2]
    astar_ms = (time.perf_counter() - started) * 1000

    matrix = [[(raw[i][j] + raw[j][i]) / 2 for j in range(size)] for i in range(size)]
    snap_m = [
        haversine(p["lat"], p["lng"], graph.lat[u], graph.lng[u]) for p, u in zip(points, snapped)
    ]
    stats = {
        "graph_nodes": len(graph),
        "graph_edges": sum(len(edges) for edges in graph.adjacency),
        "core_nodes": len(loaded.core),
        "dijkstra_ms": dijkstra_ms,
        "dijkstra_searches": size,
        "dijkstra_settled": dijkstra_settled,
        "astar_ms": astar_ms,
        "astar_searches": size * (size - 1),
        "astar_settled": astar_settled,
        "largest_snap_m": max(snap_m),
    }
    return matrix, stats


def dijkstra_geometry(points: list[dict]) -> list[list[float]]:
    loaded = load_graph(points)
    graph = loaded.graph
    snapped = [nearest_node(graph, loaded.core, p["lat"], p["lng"]) for p in points]
    line: list[list[float]] = []
    for source, target in zip(snapped, snapped[1:]):
        _, previous, _ = dijkstra(graph, source, {target})
        path = path_from(previous, source, target)
        line.extend([graph.lat[u], graph.lng[u]] for u in path)
    return line


# ----------------------------------------------------------------- Interface


def distance_matrix(points: list[dict], source: str):
    """Returns (matrix, source actually used, path statistics, notice or None).

    If road data is unavailable the run still works, on straight-line distances,
    and the notice says so.
    """
    if source == "straight":
        return straight_matrix(points), "straight", None, None
    try:
        if source == "dijkstra":
            matrix, stats = dijkstra_matrix(points)
            return matrix, "dijkstra", stats, None
        return osrm_matrix(points), "osrm", None, None
    except RoadDataError as error:
        notice = f"Road distances are unavailable ({error}), so this run uses straight-line distances."
        return straight_matrix(points), "straight", None, notice[:500]


_geometry_cache: dict[str, list[list[float]]] = {}
_GEOMETRY_CACHE_SIZE = 500


def route_geometry(points: list[dict], source: str) -> list[list[float]]:
    """The line to draw for a route. Falls back to straight legs on failure."""
    straight = [[p["lat"], p["lng"]] for p in points]
    if source == "straight":
        return straight
    key = f"{source}:{_coordinates(points)}"
    cached = _geometry_cache.get(key)
    if cached:
        return cached
    try:
        line = dijkstra_geometry(points) if source == "dijkstra" else osrm_geometry(points)
    except RoadDataError:
        return straight
    if len(_geometry_cache) >= _GEOMETRY_CACHE_SIZE:
        _geometry_cache.pop(next(iter(_geometry_cache)))
    _geometry_cache[key] = line
    return line
