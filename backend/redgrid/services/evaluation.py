"""evaluateRoute: walk the chosen path in its real direction and fill every Route number (RedGrid Class Specification).

Definitions (documented in docs/ALGORITHMS.md):
  distanceM          ground length of the path (true anisotropic spacing)
  durationMin        walking time (Tobler, real direction) + science-stop durations
  oxygen/battery     Minetti energy x terrain factor (real direction) + stops at the work rate / suit power
  oxygenLeft/batteryLeft  capacity - (route + walk back to the nearest refill point)
  feasible           path exists and both "left" values stay at or above the reserve (capacity x reserveFraction)
  limitingResource   resource with the smaller remaining share of usable, named when below risk_margin_moderate_fraction
  terrainDifficulty  length-weighted mean energy multiplier relative to flat regolith (1.0 = flat regolith)
  scienceScore       share of the science value in the corridor that lies within science_buffer_m of the path (0-1)
  hazardCount        distinct hazards and HIGH/MEDIUM hazard warnings within hazard_near_m of the path
  dataConfidence     share of path length farther than geology_offset_m from a terrain-class boundary
  missionMatch       100 x (mission-priority cost of the best route) / (mission-priority cost of this route)
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point

from ..geo import LocalMetric, map_geometry
from types import SimpleNamespace

from scipy import ndimage

from . import routing

LABEL = {"SAFEST": "safety-first", "SHORTEST": "distance-first", "SCIENCE_FOCUSED": "science-first", "MISSION_PRIORITY": "this mission's priorities"}


def dust_status(opacity):
    """Column dust optical depth (tau). Background tau at Jezero is typically below ~1; regional storms raise it to 2+.
    Labels only; thresholds are prototype values (docs/ALGORITHMS.md)."""
    if opacity is None:
        return "Data unavailable"
    if opacity < 1.0:
        return "Background dust"
    if opacity < 2.0:
        return "Elevated dust"
    return "Dust storm conditions"


def _decimate(profile: list, n: int = 200) -> list:
    if len(profile) <= n:
        return profile
    idx = np.unique(np.linspace(0, len(profile) - 1, n).round().astype(int))
    return [profile[i] for i in idx]


def walk(cat, grid, walker, vertices):
    """Walk a polyline of cell corners in its real direction: dense points every half cell, elevation interpolated
    bilinearly, attributes from the nearest square. Returns totals and per-sample arrays."""
    rows, cols, steps = routing.densify(vertices, grid.sampling, step_m=0.5 * min(grid.sampling))
    elev_grid = np.where(np.isfinite(cat.elevation_m), cat.elevation_m, np.nanmean(cat.elevation_m))
    z = ndimage.map_coordinates(elev_grid, [rows, cols], order=1, mode="nearest")
    ri, ci = np.rint(rows).astype(int), np.rint(cols).astype(int)
    tf = np.where(np.isfinite(cat.terrain_factor[ri, ci]), cat.terrain_factor[ri, ci], 1.0)
    o2 = bat = t = energy = gain = loss = slope_len = max_slope = no_comm = 0.0
    dist = 0.0
    profile = [{"distanceM": 0.0, "elevationM": round(float(z[0]), 1)}]
    for k, L in enumerate(steps, start=1):
        rise = float(z[k] - z[k - 1])
        so2, sbat, st, se = walker.step(float(L), rise, float(tf[k]))
        o2, bat, t, energy, dist = o2 + so2, bat + sbat, t + st, energy + se, dist + float(L)
        s_deg = math.degrees(math.atan(abs(rise) / L)) if L > 0 else 0.0
        slope_len += s_deg * L
        max_slope = max(max_slope, s_deg)
        gain += max(rise, 0.0)
        loss += max(-rise, 0.0)
        if cat.no_comm[ri[k], ci[k]]:
            no_comm += L
        profile.append({"distanceM": round(dist, 1), "elevationM": round(float(z[k]), 1)})
    return SimpleNamespace(o2=o2, bat=bat, t=t, energy=energy, dist=dist, gain=gain, loss=loss, slope_len=slope_len,
                           max_slope=max_slope, no_comm=no_comm, profile=profile, ri=ri, ci=ci, steps=steps,
                           z_vertices=ndimage.map_coordinates(elev_grid, [[v[0] for v in vertices], [v[1] for v in vertices]],
                                                              order=1, mode="nearest"))


def evaluate(ctx, route_type: str, vertices: list, *, mp_cost, mp_best: float | None, provider_warnings: list[str],
             cost_provider: dict, priority_resolver: dict, cost_model_id, calculated_at: str, infeasible_reason: str | None = None) -> dict:
    cat, grid, walker, res, k = ctx.cat, ctx.grid, ctx.walker, ctx.resources, ctx.constants
    if len(vertices) == 1:                   # start and destination in the same square: still a valid LineString
        vertices = [vertices[0], vertices[0]]
    w = walk(cat, grid, walker, vertices)
    lon, lat = grid.rc_to_lonlat(np.array([v[0] for v in vertices]), np.array([v[1] for v in vertices]))
    lon, lat = list(map(float, lon)), list(map(float, lat))
    lon[0], lat[0], lon[-1], lat[-1] = ctx.start_lonlat[0], ctx.start_lonlat[1], ctx.dest_lonlat[0], ctx.dest_lonlat[1]
    filled = [float(e) for e in w.z_vertices]
    o2, bat, t, energy, dist = w.o2, w.bat, w.t, w.energy, w.dist
    gain, loss, slope_len, max_slope, no_comm_len = w.gain, w.loss, w.slope_len, w.max_slope, w.no_comm
    profile = w.profile
    uncertain_len = float(sum(L for L, r, c in zip(w.steps, w.ri[1:], w.ci[1:]) if ctx.near_boundary[r, c]))
    path_cells = list(zip(w.ri.tolist(), w.ci.tolist()))

    # science stops (work at the stop: work rate and suit power over its duration)
    stop_s = sum(a.duration_min or 0.0 for a in ctx.stops) * 60.0
    stop_o2 = walker.metabolic_rate_w * stop_s / walker.oxygen_energy_j_per_l * walker.oxygen_density_g_per_l / 1000.0
    stop_bat = walker.suit_power_w * stop_s / 3600.0
    used_o2, used_bat, used_t = o2 + stop_o2, bat + stop_bat, t + stop_s

    # walk back from the destination to the nearest refill point (real direction, smoothed the same way)
    rf = None
    back_o2 = back_bat = 0.0
    dest_cell = tuple(vertices[-1])
    if ctx.refill_mcp is not None and np.isfinite(ctx.refill_dist[dest_cell]):
        # MCP traceback runs from the source (refill point) to the given square: reverse it to walk back from the destination
        back = [tuple(int(v) for v in p) for p in ctx.refill_mcp.traceback(dest_cell)][::-1]
        back_v = routing.smooth_path(back, ctx.o2_per_m, ctx.blocked, grid.sampling) if len(back) > 2 else back
        if len(back_v) == 1:
            back_v = [back_v[0], back_v[0]]
        b = walk(cat, grid, walker, back_v)
        back_o2, back_bat = b.o2, b.bat
        refill_name = ctx.refill_names.get(tuple(back[-1]), "Refill point")
        rf = {"distanceToSafePointM": round(b.dist, 1), "returnDurationMin": round(b.t / 60.0, 1),
              "safePointName": refill_name, "refillPointName": refill_name}

    cap_o2, cap_bat = res.value("OXYGEN_KG"), res.value("BATTERY_WH")
    usable_o2, usable_bat = res.usable_oxygen_kg(), res.usable_battery_wh()
    left_o2, left_bat = cap_o2 - used_o2 - back_o2, cap_bat - used_bat - back_bat
    m_o2 = (usable_o2 - used_o2 - back_o2) / usable_o2 if usable_o2 > 0 else -1.0
    m_bat = (usable_bat - used_bat - back_bat) / usable_bat if usable_bat > 0 else -1.0
    margin = min(m_o2, m_bat)
    limiting = "OXYGEN" if m_o2 <= m_bat else "BATTERY"
    feasible = infeasible_reason is None and rf is not None and margin >= 0
    if infeasible_reason is None and rf is None:
        infeasible_reason = "No refill point can be reached from the destination"
    if infeasible_reason is None and margin < 0:
        infeasible_reason = f"{'Oxygen' if limiting == 'OXYGEN' else 'Battery'} would fall below the reserve before reaching a refill point"
    if margin >= k("risk_margin_moderate_fraction") and feasible:
        limiting = "NONE"
    per_m_o2 = (usable_o2 - used_o2) / walker.oxygen_per_m_flat if walker.oxygen_per_m_flat > 0 else 0
    per_m_bat = (usable_bat - used_bat) / walker.battery_per_m_flat if walker.battery_per_m_flat > 0 else 0
    max_return = max(0.0, min(per_m_o2, per_m_bat))
    if rf is None:
        rf = {"distanceToSafePointM": None, "returnDurationMin": None, "safePointName": None, "refillPointName": None}
    rf.update({"feasible": feasible, "maximumReturnDistanceM": round(max_return, 1),
               "reason": "Within oxygen and battery budget" if feasible else infeasible_reason,
               "limitingResource": limiting})

    # features near the path (local metres)
    lm = LocalMetric(ctx.start_lonlat[0], ctx.start_lonlat[1])
    to_xy = lambda g: map_geometry(g, lm.to_xy)
    line = to_xy(LineString(list(zip(lon, lat)))) if len(lon) > 1 else to_xy(Point(lon[0], lat[0]))
    near = k("hazard_near_m")
    hazards = sum(1 for g in ctx.hazard_shapes if line.distance(to_xy(g)) < near)
    hazards += sum(1 for w in ctx.warnings if w.severity in ("HIGH", "MEDIUM") and
                   line.distance(to_xy(Point(w.lon, w.lat))) < near + (w.radius_m or 0))
    sb = k("science_buffer_m")
    total_sci = sum(v for _, v in ctx.science)
    passed = sum(v for g, v in ctx.science if line.distance(to_xy(g)) < sb)
    science = round(passed / total_sci, 3) if total_sci > 0 else 0.0

    terrain_difficulty = energy / (walker.energy_per_m_flat * dist) if dist > 0 else 1.0
    comm_share = no_comm_len / dist if dist > 0 else 0.0
    data_conf = 1.0 - uncertain_len / dist if dist > 0 else 1.0
    mm = 100.0
    no_path = infeasible_reason is not None and ("No walkable path" in infeasible_reason or "blocked ground" in infeasible_reason)
    if no_path:
        mm = 0.0                  # nothing to match: the line shown is only the straight start-destination link
        warnings_no_path = ["No route found: the line shown is the straight link between start and destination, not a walkable path"]
    else:
        warnings_no_path = []
    if mp_best is not None and len(vertices) > 1 and not no_path:
        c = routing.polyline_cost(mp_cost, vertices, grid.sampling)
        mm = 100.0 * mp_best / c if c > 0 and np.isfinite(c) else 0.0

    # risk (thresholds: planning constants and the slope-band edges of the categories)
    pc = tuple(np.array(path_cells).T)
    in_near_band = bool(np.any(cat.has("hazard_0_50")[pc]))
    in_far_band = bool(np.any(cat.has("hazard_50_200")[pc]))
    if not feasible:
        risk = "CRITICAL"
    elif margin < k("risk_margin_high_fraction") or in_near_band or hazards > 0 or max_slope >= 15:
        risk = "HIGH"
    elif margin < k("risk_margin_moderate_fraction") or in_far_band or max_slope >= 10 or comm_share > 0:
        risk = "MODERATE"
    else:
        risk = "LOW"

    warnings = list(provider_warnings) + warnings_no_path
    if not feasible:
        warnings.append(f"Not feasible: {infeasible_reason}")
    if comm_share > 0:
        warnings.append(f"{comm_share * 100:.0f}% of the route has no line of sight to a communication asset")
    if in_near_band:
        warnings.append(f"The route passes within {near:.0f} m of a hazard")
    if data_conf < 1:
        warnings.append(f"{(1 - data_conf) * 100:.0f}% of the route is near a terrain-class boundary of the geologic map (100-200 m offset)")
    if ctx.extra_warnings:
        warnings.extend(ctx.extra_warnings)

    avg_slope = slope_len / dist if dist > 0 else 0.0
    if feasible:
        rec = f"Recommended for a {LABEL[route_type]} mission" if route_type != "MISSION_PRIORITY" else "Best match for this mission's priorities"
    else:
        rec = "Not recommended: " + infeasible_reason
    return {
        "routeType": route_type,
        "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6), round(e, 1)] for x, y, e in zip(lon, lat, filled)]},
        "elevationProfile": _decimate(profile),
        "feasible": feasible, "overallRisk": risk, "missionMatch": round(float(np.clip(mm, 0, 100)), 1),
        "distanceM": round(dist, 1), "durationMin": round(used_t / 60.0, 1),
        "averageSlopeDeg": round(avg_slope, 2), "maxSlopeDeg": round(max_slope, 2),
        "elevationGainM": round(gain, 1), "elevationLossM": round(loss, 1),
        "terrainDifficulty": round(terrain_difficulty, 3), "hazardCount": int(hazards), "scienceScore": science,
        "oxygenUsedKg": round(used_o2, 4), "batteryUsedWh": round(used_bat, 1),
        "oxygenLeftKg": round(left_o2, 4), "batteryLeftWh": round(left_bat, 1),
        "costModelId": cost_model_id, "costProvider": cost_provider, "priorityResolver": priority_resolver,
        "window": ctx.window.as_dict(), "calculatedAt": calculated_at,
        "assessment": {"dustStatus": ctx.dust_status,
                       "communicationStatus": "Full coverage" if comm_share == 0 else
                       (f"Partial coverage ({comm_share * 100:.0f}% without line of sight)" if comm_share < 0.5 else
                        f"Mostly without coverage ({comm_share * 100:.0f}%)"),
                       "dataConfidence": round(data_conf, 3)},
        "returnFeasibility": rf, "warnings": warnings, "recommendation": rec,
    }
