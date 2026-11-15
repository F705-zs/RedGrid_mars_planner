"""Routing maths (RedGrid Class Specification: effectiveCost, hard mask, physical return limit, least-cost path).

Least-cost paths: Dijkstra's algorithm on the 8-connected grid (scikit-image MCP_Geometric). The cost of a move
between two squares is the mean of their per-metre costs times the true ground length of the move, with the
grid's anisotropic spacing (dy = 8 m, dx = 8 cos(lat) m) so diagonal moves are sqrt(dx^2 + dy^2) long.
"""
from __future__ import annotations

import math

import numpy as np
from skimage.graph import MCP_Geometric

from ..enums import GROUPS
from ..physics import WalkingModel


# ---------------------------------------------------------------- base cost (physics + simple additive weighting)
def resource_rates(cat, walker: WalkingModel):
    """Per-metre oxygen (kg), battery (Wh) and pace (s) on the grid, direction-free."""
    tf = np.where(np.isfinite(cat.terrain_factor), cat.terrain_factor, 1.0)
    slope = np.where(np.isfinite(cat.slope_deg), cat.slope_deg, 0.0)
    return walker.grid_rates(slope, tf)


def resource_share(o2_m, bat_m, walker: WalkingModel, usable_o2: float, usable_bat: float):
    """Share of the usable oxygen and battery used per metre, normalised to 1 on flat regolith."""
    u_o2, u_bat = max(usable_o2, 1e-12), max(usable_bat, 1e-12)
    flat = walker.oxygen_per_m_flat / u_o2 + walker.battery_per_m_flat / u_bat
    return (o2_m / u_o2 + bat_m / u_bat) / flat


def base_cost(distance_weight: float, share: np.ndarray) -> np.ndarray:
    """d x distance + (1 - d) x resource share; both terms are 1 per metre on flat regolith."""
    return distance_weight + (1.0 - distance_weight) * share


# ---------------------------------------------------------------- weighted product model with route-type limits
def effective_log(L: np.ndarray, scales: dict, rules: dict, hazard_floor: float) -> np.ndarray:
    """Sum over groups of E_g = clamp(s_g x L_g, -ln M_g, +ln M_g), with the uncertainty floor and the science limit."""
    E = np.zeros(L.shape[1:], dtype=np.float64)
    per = {}
    for gi, g in enumerate(GROUPS):
        s, M = float(scales[g]), float(rules[g].max_factor)
        cap = math.log(M)
        Eg = np.clip(s * L[gi].astype(np.float64), -cap, cap)
        if g == "UNCERTAINTY":
            Eg = np.maximum(Eg, 0.0)          # missing data is never made cheaper
        per[g] = Eg
    v = rules["SCIENCE"].max_vs_hazard
    if v is not None:
        h = min(float(scales["HAZARD"]) * hazard_floor, math.log(float(rules["HAZARD"].max_factor)))
        per["SCIENCE"] = np.maximum(per["SCIENCE"], -float(v) * h)   # a science pull never beats the weakest hazard push
    for Eg in per.values():
        E += Eg
    return E


def route_scales(profile, resolved) -> dict:
    """Exponent per group: the rule's scale, or the priority resolver's value when the rule leaves it empty."""
    by = resolved.by_group() if resolved is not None else {}
    return {r.group: (r.scale if r.scale is not None else by[r.group]) for r in profile.rules}


# ---------------------------------------------------------------- hard limits and the physical return limit
def hard_mask(cat, max_slope_deg: float, extra_core: np.ndarray | None = None) -> np.ndarray:
    blocked = ~cat.routable | ~(np.nan_to_num(cat.slope_deg, nan=90.0) <= max_slope_deg) | cat.hazard_core
    if extra_core is not None:
        blocked |= extra_core
    return blocked


def _field(cost_per_m: np.ndarray, blocked: np.ndarray, sources: list, sampling):
    c = np.where(blocked, np.inf, cost_per_m)
    m = MCP_Geometric(c, fully_connected=True, sampling=sampling)
    d, _ = m.find_costs([tuple(s) for s in sources])
    return d, m


def return_limit(o2_m, bat_m, blocked, start, refills, usable_o2, usable_bat, sampling):
    """Squares the crew can reach from the start and still walk to the nearest refill point within the usable
    oxygen AND battery. Returns (ok mask, oxygen-to-refill MCP for tracing the walk back)."""
    d_o2_s, _ = _field(o2_m, blocked, [start], sampling)
    d_bat_s, _ = _field(bat_m, blocked, [start], sampling)
    d_o2_r, m_ref = _field(o2_m, blocked, refills, sampling)
    d_bat_r, _ = _field(bat_m, blocked, refills, sampling)
    ok = (d_o2_s + d_o2_r <= usable_o2) & (d_bat_s + d_bat_r <= usable_bat)
    return ok, m_ref, d_o2_r


# ---------------------------------------------------------------- least-cost path through ordered waypoints
def least_cost_path(cost_per_m: np.ndarray, blocked: np.ndarray, points: list, sampling):
    """Dijkstra leg by leg through the waypoints. Returns the list of (row, col) or None if a leg is impossible."""
    c = np.where(blocked, np.inf, cost_per_m)
    path: list = []
    for a, b in zip(points[:-1], points[1:]):
        if tuple(a) == tuple(b):
            continue
        m = MCP_Geometric(c, fully_connected=True, sampling=sampling)
        d, _ = m.find_costs([tuple(a)], [tuple(b)])
        if not np.isfinite(d[tuple(b)]):
            return None
        leg = [tuple(p) for p in m.traceback(tuple(b))]
        path.extend(leg if not path else leg[1:])
    return path or [tuple(points[0])]


def path_cost(cost_per_m: np.ndarray, path: list, sampling) -> float:
    """Integral of a per-metre cost along a path (same rule as MCP_Geometric: mean of the two squares x length)."""
    dy, dx = sampling
    total = 0.0
    for (r0, c0), (r1, c1) in zip(path[:-1], path[1:]):
        L = math.hypot((r1 - r0) * dy, (c1 - c0) * dx)
        total += 0.5 * (cost_per_m[r0, c0] + cost_per_m[r1, c1]) * L
    return total


def touches_edge(path: list, shape, open_edges: dict) -> bool:
    H, W = shape
    for r, c in path:
        if (r == 0 and open_edges["north"]) or (r == H - 1 and open_edges["south"]) or \
           (c == 0 and open_edges["west"]) or (c == W - 1 and open_edges["east"]):
            return True
    return False


# ---------------------------------------------------------------- safe path smoothing (cost-aware string pulling)
def _samples(a, b, sampling, step_cells: float = 0.25):
    """Continuous (row, col) points from a to b, every step_cells of the smaller cell side (both ends included)."""
    dy, dx = sampling
    (r0, c0), (r1, c1) = a, b
    n = max(1, int(np.ceil(max(abs(r1 - r0), abs(c1 - c0)) / step_cells)))
    t = np.linspace(0.0, 1.0, n + 1)
    return r0 + t * (r1 - r0), c0 + t * (c1 - c0), math.hypot((r1 - r0) * dy, (c1 - c0) * dx)


def line_cost(cost_per_m: np.ndarray, a, b, sampling) -> float:
    """Integral of a per-metre cost along the straight segment a-b. Midpoint rule on 1/4-cell sub-intervals, so no
    sample lands exactly on a square's edge or corner; one grid step costs exactly what Dijkstra charged for it."""
    (r0, c0), (r1, c1) = a, b
    dy, dx = sampling
    L = math.hypot((r1 - r0) * dy, (c1 - c0) * dx)
    n = max(1, int(np.ceil(max(abs(r1 - r0), abs(c1 - c0)) / 0.25)))
    t = (np.arange(n) + 0.5) / n
    v = cost_per_m[np.rint(r0 + t * (r1 - r0)).astype(int), np.rint(c0 + t * (c1 - c0)).astype(int)]
    return float(v.mean() * L)


def segment_clear(blocked: np.ndarray, a, b, sampling) -> bool:
    """True when the segment touches no blocked square. Samples every 1/4 cell; a sample lying exactly on an edge or a
    corner checks every square touching that point, so a shortcut never squeezes between two blocked squares."""
    rr, cc, _ = _samples(a, b, sampling)
    eps = 1e-9
    rows = (np.floor(rr + 0.5 - eps).astype(int), np.floor(rr + 0.5 + eps).astype(int))
    cols = (np.floor(cc + 0.5 - eps).astype(int), np.floor(cc + 0.5 + eps).astype(int))
    H, W = blocked.shape
    for r in rows:
        for c in cols:
            if blocked[np.clip(r, 0, H - 1), np.clip(c, 0, W - 1)].any():
                return False
    return True


def smooth_path(path: list, cost_per_m: np.ndarray, blocked: np.ndarray, sampling, keep=frozenset()) -> list:
    """Remove staircase corners from a grid path. A shortcut p_i -> p_j is taken only if it crosses no blocked square
    and costs no more than the grid path it replaces (so the route stays as safe and as good). Points in `keep`
    (science stops) always stay. Returns a subset of the path's cells as the route's corners."""
    if len(path) <= 2:
        return list(path)
    dy, dx = sampling
    cum = [0.0]
    for (r0, c0), (r1, c1) in zip(path[:-1], path[1:]):
        L = math.hypot((r1 - r0) * dy, (c1 - c0) * dx)
        cum.append(cum[-1] + 0.5 * (cost_per_m[r0, c0] + cost_per_m[r1, c1]) * L)
    cuts = [0] + [k for k in range(1, len(path) - 1) if tuple(path[k]) in keep] + [len(path) - 1]

    def ok(i, j):
        return segment_clear(blocked, path[i], path[j], sampling) and \
            line_cost(cost_per_m, path[i], path[j], sampling) <= (cum[j] - cum[i]) * (1 + 1e-9) + 1e-12

    out = [0]
    for s, e in zip(cuts[:-1], cuts[1:]):
        i = s
        while i < e:
            best, step = i + 1, 2
            while i + step <= e and ok(i, i + step):        # exponential search ...
                best, step = i + step, step * 2
            lo, hi = best, min(i + step, e + 1)
            while hi - lo > 1:                              # ... then binary search for the farthest valid corner
                mid = (lo + hi) // 2
                if ok(i, mid):
                    lo = mid
                else:
                    hi = mid
            out.append(lo)
            i = lo
    return [tuple(path[k]) for k in out]


def densify(vertices: list, sampling, step_m: float):
    """Points along a polyline of cell corners, at most step_m apart: (rows, cols) as floats, plus step lengths (m)."""
    dy, dx = sampling
    rows, cols = [float(vertices[0][0])], [float(vertices[0][1])]
    steps = []
    for (r0, c0), (r1, c1) in zip(vertices[:-1], vertices[1:]):
        L = math.hypot((r1 - r0) * dy, (c1 - c0) * dx)
        n = max(1, int(math.ceil(L / step_m)))
        for k in range(1, n + 1):
            t = k / n
            rows.append(r0 + t * (r1 - r0))
            cols.append(c0 + t * (c1 - c0))
            steps.append(L / n)
    return np.array(rows), np.array(cols), np.array(steps)


def polyline_cost(cost_per_m: np.ndarray, vertices: list, sampling) -> float:
    return sum(line_cost(cost_per_m, a, b, sampling) for a, b in zip(vertices[:-1], vertices[1:]))
