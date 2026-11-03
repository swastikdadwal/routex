import itertools
import math
import random

import pytest

from app.algorithms.shortest_path import RoadGraph, astar, dijkstra, path_from, strongly_connected_core
from app.algorithms.solvers import (
    EXECUTION_ORDER,
    Instance,
    approximation,
    assign_cheapest,
    brute_force_plan_count,
    lower_bound,
    route_length,
    solve,
)


def random_instance(rng, n, capacities=None, m=None, slack=1.4):
    points = [(5000, 5000)] + [(rng.random() * 10000, rng.random() * 10000) for _ in range(n)]
    dist = [[math.dist(a, b) for b in points] for a in points]
    demand = [0] + [rng.randint(1, 3) for _ in range(n)]
    if capacities is None:
        m = m or rng.randint(1, 3)
        total = sum(demand)
        base = max(3, math.ceil(total * slack / m))
        # Mixed fleets are the case equal-capacity shortcuts get wrong.
        capacities = [max(1, base + rng.randint(-2, 2)) for _ in range(m)]
    return Instance(dist, demand, capacities)


def oracle(inst):
    """Independent optimum: all order permutations, all assignments to vehicles."""
    best = math.inf
    for assignment in itertools.product(range(inst.m), repeat=inst.n):
        groups = [[] for _ in range(inst.m)]
        loads = [0] * inst.m
        for index, vehicle in enumerate(assignment):
            groups[vehicle].append(index + 1)
            loads[vehicle] += inst.demand[index + 1]
        if any(load > cap for load, cap in zip(loads, inst.capacities)):
            continue
        total = 0.0
        for group in groups:
            total += min((route_length(inst.dist, list(p)) for p in itertools.permutations(group)), default=0.0)
        best = min(best, total)
    return best


def assert_valid(inst, result):
    assert len(result.routes) == inst.m
    seen = []
    for vehicle, route in enumerate(result.routes):
        assert sum(inst.demand[o] for o in route) <= inst.capacities[vehicle], "vehicle over capacity"
        seen += route
    assert len(seen) == len(set(seen)), "order served twice"
    assert not set(seen) & set(result.unserved), "order both served and unserved"
    assert sorted(seen + result.unserved) == list(range(1, inst.n + 1))
    total = sum(route_length(inst.dist, route) for route in result.routes)
    assert total == pytest.approx(result.distance)


def test_exact_solvers_match_independent_oracle():
    rng = random.Random(7)
    solvable = infeasible = 0
    for _ in range(150):
        inst = random_instance(rng, rng.randint(1, 6), slack=rng.uniform(0.7, 1.7))
        truth = oracle(inst)
        for name in EXECUTION_ORDER:
            assert_valid(inst, solve(name, inst, 30))
        results = {name: solve(name, inst, 30) for name in ("dp", "bnb", "brute")}
        if truth == math.inf:
            infeasible += 1
            for name, result in results.items():
                assert result.infeasible, name
            continue
        solvable += 1
        for name, result in results.items():
            assert result.optimal and not result.unserved, name
            assert result.distance == pytest.approx(truth), name
        for name in ("greedy", "approx"):
            heuristic = solve(name, inst)
            if not heuristic.unserved:
                assert heuristic.distance >= truth - 1e-6, name
        assert lower_bound(inst) <= truth + 1e-6
    assert solvable > 50 and infeasible > 5


def test_routes_belong_to_the_callers_vehicle_order():
    # The large order only fits the large vehicle, which is listed last.
    dist = [[0, 10, 10], [10, 0, 5], [10, 5, 0]]
    inst = Instance(dist, [0, 5, 1], [1, 5])
    for name in EXECUTION_ORDER:
        result = solve(name, inst)
        assert 1 in result.routes[1], name


def test_a_small_vehicle_can_take_a_subset_without_the_lowest_order():
    # Regression for the equal-capacity shortcut: the best plan gives order 1 to
    # the big vehicle and orders 2 and 3 to the small one.
    points = [(0, 0), (-100, 0), (100, 0), (110, 0)]
    dist = [[math.dist(a, b) for b in points] for a in points]
    inst = Instance(dist, [0, 3, 1, 1], [3, 2])
    assert solve("dp", inst).distance == pytest.approx(oracle(inst))
    assert solve("bnb", inst).distance == pytest.approx(oracle(inst))


def test_dp_and_branch_and_bound_agree_above_oracle_range():
    rng = random.Random(11)
    for _ in range(5):
        inst = random_instance(rng, 9, m=3)
        assert solve("dp", inst, 60).distance == pytest.approx(solve("bnb", inst, 60).distance)


def test_approximation_tour_within_twice_optimal():
    rng = random.Random(3)
    worst = 0.0
    for _ in range(60):
        inst = random_instance(rng, rng.randint(3, 9), capacities=[10_000])
        ratio = approximation(inst).distance / solve("dp", inst).distance
        worst = max(worst, ratio)
    assert worst <= 2 + 1e-9


def test_time_limit_is_respected_and_reported():
    inst = random_instance(random.Random(5), 30, m=4)
    result = solve("bnb", inst, 0.2)
    assert result.timed_out and not result.optimal
    assert result.elapsed_ms < 1500
    assert_valid(inst, result)


def test_size_gates_skip_instead_of_hanging():
    inst = random_instance(random.Random(5), 30, m=4)
    assert solve("dp", inst).skipped
    assert solve("brute", inst).skipped
    assert brute_force_plan_count(3, 2) == 24


def test_zero_orders_and_an_order_too_large_for_any_vehicle():
    empty = Instance([[0.0]], [0], [5, 5])
    for name in EXECUTION_ORDER:
        result = solve(name, empty)
        assert result.distance == 0 and not result.unserved, name
    huge = Instance([[0, 10], [10, 0]], [0, 9], [5, 5])
    assert solve("dp", huge).infeasible and solve("bnb", huge).infeasible and solve("brute", huge).infeasible
    assert solve("greedy", huge).unserved == [1] and solve("approx", huge).unserved == [1]


def test_assign_cheapest_matches_every_permutation():
    rng = random.Random(21)
    for _ in range(200):
        vehicles = rng.randint(1, 5)
        routes = rng.randint(1, vehicles)
        capacities = [rng.randint(3, 9) for _ in range(vehicles)]
        rates = [rng.uniform(0, 3) for _ in range(vehicles)]
        loads = [rng.randint(1, 9) for _ in range(routes)]
        distances = [rng.uniform(1, 100) for _ in range(routes)]
        options = [
            sum(d * rates[v] for d, v in zip(distances, chosen))
            for chosen in itertools.permutations(range(vehicles), routes)
            if all(load <= capacities[v] for load, v in zip(loads, chosen))
        ]
        assignment = assign_cheapest(loads, distances, capacities, rates)
        if not options:
            assert assignment == []
            continue
        assert len(set(assignment)) == routes
        assert all(load <= capacities[v] for load, v in zip(loads, assignment))
        assert sum(d * rates[v] for d, v in zip(distances, assignment)) == pytest.approx(min(options))


def grid_graph(size, rng):
    graph = RoadGraph()
    for r in range(size):
        for c in range(size):
            graph.add_node(12.9 + r * 0.001 + rng.random() * 2e-4, 77.5 + c * 0.001 + rng.random() * 2e-4)
    for r in range(size):
        for c in range(size):
            u = r * size + c
            if c + 1 < size:
                graph.add_edge(u, u + 1, oneway=rng.random() < 0.2)
            if r + 1 < size:
                graph.add_edge(u, u + size, oneway=rng.random() < 0.2)
    return graph


def bellman_ford(graph, source):
    distance = [math.inf] * len(graph)
    distance[source] = 0.0
    for _ in range(len(graph)):
        changed = False
        for u, edges in enumerate(graph.adjacency):
            for v, length in edges:
                if distance[u] + length < distance[v] - 1e-12:
                    distance[v] = distance[u] + length
                    changed = True
        if not changed:
            break
    return distance


def test_dijkstra_and_astar_match_bellman_ford():
    rng = random.Random(9)
    graph = grid_graph(14, rng)
    total_astar = total_dijkstra = 0
    for _ in range(40):
        source, target = rng.randrange(len(graph)), rng.randrange(len(graph))
        truth = bellman_ford(graph, source)[target]
        distance, previous, settled = dijkstra(graph, source, {target})
        assert distance[target] == pytest.approx(truth)
        cost, path, astar_settled = astar(graph, source, target)
        assert cost == pytest.approx(truth)
        if truth < math.inf:
            total_astar += astar_settled
            total_dijkstra += settled
            for walked in (path, path_from(previous, source, target)):
                assert walked[0] == source and walked[-1] == target
                length = sum(dict(graph.adjacency[a])[b] for a, b in zip(walked, walked[1:]))
                assert length == pytest.approx(truth)
    assert total_astar < total_dijkstra, "A* should settle fewer nodes"


def test_one_way_streets_are_respected():
    graph = RoadGraph()
    a, b, c = (graph.add_node(12.9, 77.5 + i * 0.01) for i in range(3))
    graph.add_edge(a, b, oneway=True)
    graph.add_edge(b, c)
    assert dijkstra(graph, a)[0][c] < math.inf
    assert dijkstra(graph, c)[0][a] == math.inf
    assert astar(graph, c, a)[0] == math.inf


def test_core_excludes_nodes_that_cannot_return():
    graph = RoadGraph()
    nodes = [graph.add_node(12.9, 77.5 + i * 0.01) for i in range(5)]
    graph.add_edge(nodes[0], nodes[1])
    graph.add_edge(nodes[1], nodes[2])
    graph.add_edge(nodes[2], nodes[3])
    graph.add_edge(nodes[3], nodes[4], oneway=True)  # dead end: 4 can never return
    assert strongly_connected_core(graph) == set(nodes[:4])
