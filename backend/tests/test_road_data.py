import math

import httpx
import pytest

from app import road_data
from app.algorithms.shortest_path import dijkstra
from app.config import settings
from app.road_data import RoadDataError, _download_roads, distance_matrix, parse_overpass, straight_matrix


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


ROADS = {"elements": [way([1, 2])]}


@pytest.fixture()
def servers(monkeypatch):
    """Answers road downloads from a script, and records which server was asked."""
    asked = []
    script = []

    def fake_post(url, **_):
        asked.append(url)
        answer = script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        request = httpx.Request("POST", url)
        if isinstance(body, str):
            return httpx.Response(status, text=body, request=request)
        return httpx.Response(status, json=body, request=request)

    monkeypatch.setattr(road_data.httpx, "post", fake_post)
    monkeypatch.setattr(road_data.time, "sleep", lambda _: None)
    monkeypatch.setattr(settings, "overpass_url", "https://main")
    monkeypatch.setattr(settings, "overpass_backup_urls", ["https://backup"])
    return asked, script


def test_download_moves_to_the_backup_when_the_main_server_fails(servers):
    asked, script = servers
    script.extend([(502, "<html>Bad Gateway</html>"), (200, ROADS)])
    assert _download_roads("query") == ROADS["elements"]
    assert asked == ["https://main", "https://backup"]


@pytest.mark.parametrize(
    "failure",
    [
        (429, "slow down"),
        (504, "timeout"),
        (200, "<html>not json</html>"),
        (200, {"elements": [], "remark": "runtime error: Query timed out"}),
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("refused"),
    ],
)
def test_each_kind_of_server_trouble_is_retried(servers, failure):
    asked, script = servers
    script.extend([failure, (200, ROADS)])
    assert _download_roads("query") == ROADS["elements"]
    assert len(asked) == 2


def test_download_tries_again_after_a_wait_when_every_server_fails(servers):
    asked, script = servers
    script.extend([(502, "x"), (502, "x"), (200, ROADS)])
    assert _download_roads("query") == ROADS["elements"]
    assert asked == ["https://main", "https://backup", "https://main"]


def test_download_gives_up_after_its_rounds_with_a_short_message(servers):
    asked, script = servers
    script.extend([(502, "x")] * 4)
    with pytest.raises(RoadDataError) as error:
        _download_roads("query")
    assert len(asked) == 4
    assert "HTTP 502" in str(error.value) and "http" not in str(error.value)


def test_download_stops_at_its_time_budget(servers, monkeypatch):
    asked, script = servers
    monkeypatch.setattr(road_data, "OVERPASS_TOTAL_BUDGET_S", 0)
    with pytest.raises(RoadDataError):
        _download_roads("query")
    assert asked == []


def test_a_refused_request_is_not_retried(servers):
    asked, script = servers
    script.append((400, "bad query"))
    with pytest.raises(RoadDataError):
        _download_roads("query")
    assert asked == ["https://main"]


def test_empty_area_without_a_remark_is_a_real_answer(servers):
    asked, script = servers
    script.append((200, {"elements": []}))
    assert _download_roads("query") == []
    assert asked == ["https://main"]


def test_run_falls_back_to_straight_lines_and_says_so_when_all_servers_fail(servers, monkeypatch):
    _, script = servers
    script.extend([(502, "x")] * 4)
    monkeypatch.setattr(road_data, "_graph_cache", [])
    points = [{"lat": 40.0, "lng": 10.0}, {"lat": 40.1, "lng": 10.0}]
    matrix, used, stats, notice = distance_matrix(points, "dijkstra")
    assert used == "straight" and stats is None and matrix == straight_matrix(points)
    assert "straight-line" in notice and "busy" in notice and "mozilla" not in notice


def test_straight_matrix_is_symmetric_and_plausible():
    points = [{"lat": 12.9716, "lng": 77.5946}, {"lat": 13.0716, "lng": 77.5946}]
    matrix = straight_matrix(points)
    assert matrix[0][0] == 0
    assert matrix[0][1] == matrix[1][0]
    assert 11000 < matrix[0][1] < 11200  # 0.1 degrees of latitude is about 11.1 km
