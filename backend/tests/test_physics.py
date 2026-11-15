import math

import numpy as np
import pytest

from redgrid.physics import C0, WalkingModel, energy_ratio_symmetric, minetti_cost, pace_ratio_symmetric, tobler_relative_speed

W = WalkingModel(300, 3 / 3.6, 90, 20100, 1.429)


def test_minetti_published_values():
    assert C0 == pytest.approx(2.5)
    assert float(minetti_cost(0.364)) == pytest.approx(13.57, abs=0.01)
    xs = np.linspace(-0.45, 0.45, 9001)
    assert xs[np.argmin(minetti_cost(xs))] == pytest.approx(-0.153, abs=0.01)   # cheapest walking is gently downhill


def test_symmetric_energy_at_limit():
    assert float(energy_ratio_symmetric(math.tan(math.radians(20)))) == pytest.approx(3.34, abs=0.01)
    assert float(energy_ratio_symmetric(0.0)) == pytest.approx(1.0)


def test_tobler_relative_speed():
    assert float(tobler_relative_speed(0.0)) == pytest.approx(1.0)
    assert float(tobler_relative_speed(-0.05)) > 1.0                   # fastest just downhill
    assert float(pace_ratio_symmetric(0.0)) == pytest.approx(1.0)


def test_oxygen_rate_matches_draft_range():
    kg_per_h = W.oxygen_per_m_flat * W.walk_speed_flat_ms * 3600
    assert 0.07 <= kg_per_h <= 0.09                                   # Project draft: about 0.07-0.09 kg/h


def test_round_trip_equals_symmetric_grid():
    """Up then down a constant slope uses exactly twice the direction-free grid energy."""
    L, rise = 100.0, 25.0
    up = W.step(L, rise, 1.0)
    down = W.step(L, -rise, 1.0)
    o2_grid, _, _ = W.grid_rates(np.array([math.degrees(math.atan(rise / L))]), np.array([1.0]))
    assert up[0] + down[0] == pytest.approx(2 * o2_grid[0] * L, rel=1e-9)
