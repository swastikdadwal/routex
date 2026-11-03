import math

from app.algorithms.shortest_path import dijkstra
from app.road_data import parse_overpass, straight_matrix


def way(nodes, tags=None, geometry=None):
    return {
        "type": "way",
        "nodes": nodes,
        "tags": {"highway": "residential", **(tags or {})},
        "geometry": geometry or [{"lat": 12.9, "lon": 77.5 + i * 0.001} for i in range(len(nodes))],
    }


def reachable_both_ways(graph):
    return dijkstra(graph, 0)[0][1] < math.inf, dijkstra(graph, 1)[0][0] < math.inf


def test_two_way_road():
    assert reachable_both_ways(parse_overpass([way([1, 2])])) == (True, True)


def test_oneway_tags():
    assert reachable_both_ways(parse_overpass([way([1, 2], {"oneway": "yes"})])) == (True, False)
    assert reachable_both_ways(parse_overpass([way([1, 2], {"oneway": "-1"})])) == (False, True)
    assert reachable_both_ways(parse_overpass([way([1, 2], {"junction": "roundabout"})])) == (True, False)
    assert reachable_both_ways(parse_overpass([way([1, 2], {"highway": "motorway"})])) == (True, False)
    assert reachable_both_ways(parse_overpass([way([1, 2], {"highway": "motorway", "oneway": "no"})])) == (True, True)


def test_shared_nodes_join_ways_into_one_network():
    graph = parse_overpass([way([1, 2]), way([2, 3])])
    assert len(graph) == 3
    assert dijkstra(graph, 0)[0][2] < math.inf


def test_nodes_outside_the_query_area_are_skipped():
    geometry = [{"lat": 12.9, "lon": 77.5}, None, {"lat": 12.9, "lon": 77.502}]
    graph = parse_overpass([way([1, 2, 3], geometry=geometry)])
    assert len(graph) == 2
    assert dijkstra(graph, 0)[0][1] == math.inf


def test_straight_matrix_is_symmetric_and_plausible():
    points = [{"lat": 12.9716, "lng": 77.5946}, {"lat": 13.0716, "lng": 77.5946}]
    matrix = straight_matrix(points)
    assert matrix[0][0] == 0
    assert matrix[0][1] == matrix[1][0]
    assert 11000 < matrix[0][1] < 11200  # 0.1 degrees of latitude is about 11.1 km
