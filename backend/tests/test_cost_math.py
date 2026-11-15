import math

import numpy as np
import pytest

from redgrid.enums import GROUPS
from redgrid.models import ProfileRule
from redgrid.providers.contracts import PriorityRequest
from redgrid.providers.priority import AlgorithmPriorityResolver
from redgrid.services import routing


def rules(**over):
    base = {"HAZARD": (1, 50, None), "TERRAIN": (1, 20, None), "SCIENCE": (1, 10, 1.0), "COMMUNICATION": (1, 10, None),
            "UNCERTAINTY": (1, 50, None), "ROVER_PATH": (1, 2, None)}
    base.update(over)
    return {g: ProfileRule("X", g, s, m, v) for g, (s, m, v) in base.items()}


def L_with(group, value):
    L = np.zeros((6, 1, 1), np.float32)
    L[GROUPS.index(group)] = value
    return L


def test_cap_prevents_overflow():
    scales = {g: 1.0 for g in GROUPS} | {"HAZARD": 3.15}
    E = routing.effective_log(L_with("HAZARD", math.log(4)), scales, rules(), hazard_floor=math.log(1.5))
    assert math.exp(E[0, 0]) == pytest.approx(50.0)          # 4 ** 3.15 = 78.8 is capped at maxFactor 50


def test_uncertainty_never_cheaper():
    E = routing.effective_log(L_with("UNCERTAINTY", -2.0), {g: 1.0 for g in GROUPS}, rules(), math.log(1.5))
    assert E[0, 0] == 0.0


def test_science_never_beats_weakest_hazard():
    scales = {g: 1.0 for g in GROUPS} | {"HAZARD": 2.0, "SCIENCE": 2.0}
    r = rules(SCIENCE=(None, 10, 0.5))
    E = routing.effective_log(L_with("SCIENCE", math.log(0.1)), scales, r, hazard_floor=math.log(1.5))
    assert E[0, 0] == pytest.approx(-0.5 * 2.0 * math.log(1.5))


def test_equal_priorities_leave_weights_unchanged():
    eq = {k: 1 / 7 for k in ["safetyWeight", "scienceWeight", "distanceWeight", "walkingDifficultyWeight", "returnWeight",
                             "environmentWeight", "roverPathWeight"]}
    s = AlgorithmPriorityResolver().resolve(PriorityRequest("CUSTOM", eq, []))
    for v in s.by_group().values():
        assert v == pytest.approx(1.0)
    assert s.distance_weight == pytest.approx(0.5)


def test_base_cost_is_one_on_flat_regolith():
    from redgrid.physics import WalkingModel
    w = WalkingModel(300, 3 / 3.6, 90, 20100, 1.429)
    share = routing.resource_share(np.array([w.oxygen_per_m_flat]), np.array([w.battery_per_m_flat]), w, 0.48, 640)
    for d in (0.0, 0.3, 1.0):
        assert routing.base_cost(d, share)[0] == pytest.approx(1.0)


def test_wall_gives_no_path():
    cost = np.ones((5, 5))
    blocked = np.zeros((5, 5), bool)
    blocked[:, 2] = True
    assert routing.least_cost_path(cost, blocked, [(0, 0), (4, 4)], (8.0, 7.59)) is None
    blocked[4, 2] = False
    p = routing.least_cost_path(cost, blocked, [(0, 0), (0, 4)], (8.0, 7.59))
    assert (4, 2) in p


# ---------------------------------------------------------------- safe smoothing
S = (8.0, 7.59)


def test_smoothing_straightens_open_ground():
    cost = np.ones((60, 60))
    blocked = np.zeros((60, 60), bool)
    path = routing.least_cost_path(cost, blocked, [(5, 5), (40, 55)], S)
    v = routing.smooth_path(path, cost, blocked, S)
    straight = math.hypot(35 * 8.0, 50 * 7.59)
    grid_len = routing.path_cost(np.ones((60, 60)), path, S)
    smooth_len = routing.polyline_cost(np.ones((60, 60)), v, S)
    assert len(v) == 2 and smooth_len == pytest.approx(straight, rel=1e-6) and grid_len > smooth_len * 1.03


def test_smoothing_never_crosses_blocked_squares_or_costs_more():
    rng = np.random.default_rng(3)
    for _ in range(20):
        cost = rng.uniform(1, 5, (50, 50))
        blocked = rng.random((50, 50)) < 0.18
        blocked[0, 0] = blocked[49, 49] = False
        path = routing.least_cost_path(cost, blocked, [(0, 0), (49, 49)], S)
        if path is None:
            continue
        v = routing.smooth_path(path, cost, blocked, S)
        # every shortcut smoothing creates (non-adjacent corners) is clear of blocked squares; single grid steps come
        # from Dijkstra itself, which may pass diagonally between two blocked squares that touch only at a corner
        made = [(a, b) for a, b in zip(v[:-1], v[1:]) if max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 1]
        assert all(routing.segment_clear(blocked, a, b, S) for a, b in made)
        assert routing.polyline_cost(cost, v, S) <= routing.path_cost(cost, path, S) * (1 + 1e-6)


def test_smoothing_keeps_stops():
    cost = np.ones((40, 40))
    blocked = np.zeros((40, 40), bool)
    stop = (30, 5)
    path = routing.least_cost_path(cost, blocked, [(0, 0), stop, (0, 39)], S)
    v = routing.smooth_path(path, cost, blocked, S, keep=frozenset([stop]))
    assert v == [(0, 0), stop, (0, 39)]


def test_smoothing_does_not_cut_a_corner_through_a_wall():
    cost = np.ones((20, 20))
    blocked = np.zeros((20, 20), bool)
    blocked[5:20, 10] = True                       # wall with a gap at the top
    path = routing.least_cost_path(cost, blocked, [(19, 0), (19, 19)], S)
    v = routing.smooth_path(path, cost, blocked, S)
    made = [(a, b) for a, b in zip(v[:-1], v[1:]) if max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 1]
    assert made and all(routing.segment_clear(blocked, a, b, S) for a, b in made)
    assert min(r for r, _ in v) <= 4                 # still goes over the top of the wall
