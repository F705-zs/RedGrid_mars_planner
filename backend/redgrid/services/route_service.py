"""RouteService.computeRoutes (RedGrid Class Specification, "How computeRoutes works")."""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from scipy import ndimage
from shapely.geometry import shape

from ..enums import ROUTE_TYPES
from ..errors import ApiError
from ..geo import BBox, LocalMetric
from ..physics import WalkingModel
from ..providers.contracts import CostRequest, PriorityRequest, catalog_version
from . import routing
from .evaluation import dust_status, evaluate


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RouteService:
    def __init__(self, *, regions, missions, routes, profiles, constants, layers, rasters, environment, cost_models,
                 extractor, cost_chain, priority_chain, mission_service):
        self.regions, self.missions, self.routes, self.profiles = regions, missions, routes, profiles
        self.k, self.layers, self.rasters, self.environment = constants, layers, rasters, environment
        self.cost_models, self.extractor = cost_models, extractor
        self.cost_chain, self.priority_chain, self.mission_service = cost_chain, priority_chain, mission_service

    # ------------------------------------------------------------------ public
    def get_routes(self, mission_id: int) -> list[dict]:
        self.missions.get_by_id(mission_id)
        return self.routes.get_by_mission(mission_id)

    def select_route(self, mission_id: int, route_id: int):
        mission = self.missions.get_by_id(mission_id)
        route = self.routes.get_by_id(route_id)
        mission.assert_owns_route(route["missionId"], route_id)
        self.missions.save_selected_route(mission_id, route_id)
        return self.missions.get_by_id(mission_id)

    def recalculate(self, mission_id: int) -> list[dict]:
        self.missions.get_by_id(mission_id).assert_editable()
        return self.compute_routes(mission_id)

    def compute_routes(self, mission_id: int) -> list[dict]:
        mission = self.missions.get_by_id(mission_id)
        region = self.regions.get_by_id(mission.region_id)
        self._check_points(mission, region)
        res = self.mission_service.get_resources(mission_id)
        walker = WalkingModel(metabolic_rate_w=res.value("METABOLIC_RATE_W"), walk_speed_flat_ms=self.k.value("walk_speed_flat_kmh") / 3.6,
                              suit_power_w=res.value("SUIT_POWER_W"), oxygen_energy_j_per_l=self.k.value("oxygen_energy_j_per_l"),
                              oxygen_density_g_per_l=self.k.value("oxygen_density_g_per_l"))

        annotations = self.missions.get_annotations(mission_id)
        extra_warnings: list[str] = []
        stops = [a for a in annotations if a.kind == "SCIENCE_STOP"]
        outside = [a for a in stops if not region.is_routable(a.lon, a.lat)]
        if outside:
            extra_warnings.append(f"{len(outside)} science stop(s) outside the routable area were skipped")
        stops = self._order_stops([a for a in stops if a not in outside], mission)
        hz_warnings = [a for a in annotations if a.kind == "HAZARD_WARNING"]

        refill_feats = [f for f in self.layers.get_refill_points(region.id) if region.is_routable(*f.geometry["coordinates"][:2])]
        refills = [(f.geometry["coordinates"][0], f.geometry["coordinates"][1], f.name or "Refill point") for f in refill_feats]
        if mission.start_is_base:
            refills.insert(0, (mission.start_lon, mission.start_lat, "Start (base)"))
        if not refills:
            extra_warnings.append("No refill point available")

        # priorities -> exponents (one call; used by MISSION_PRIORITY)
        preq = PriorityRequest(profile=mission.profile, priorities=mission.priorities.normalised().as_dict(),
                               mix=[{"presetKey": e.preset_key, "percent": e.percent} for e in mission.priority_mix])
        pres = self.priority_chain.call("resolve", preq)
        scales = pres.value
        provider_warnings = [f"Priority resolver: {s}; next provider used" for s in pres.skipped]

        profiles = {t: self.profiles.get_by_key(t) for t in ROUTE_TYPES}
        for p in profiles.values():
            if not p.validate():
                raise ApiError("INVALID_PROFILE", f"Route profile {p.key} is not valid")

        snap = self.environment.get_snapshot(region.id) or {}
        dust = dust_status(snap.get("dust_opacity"))
        max_exp = int(self.k.value("corridor_max_expansions"))
        lm = LocalMetric(mission.start_lon, mission.start_lat)
        pts = [(mission.start_lon, mission.start_lat), (mission.dest_lon, mission.dest_lat)] + [(a.lon, a.lat) for a in stops]
        if refills:   # include the refill point nearest to the destination so the walk back can be traced
            dx, dy = lm.to_xy(mission.dest_lon, mission.dest_lat)
            near = min(refills, key=lambda r: math.hypot(*(np.array(lm.to_xy(r[0], r[1])) - np.array([dx, dy]))))
            pts.append((near[0], near[1]))
        trip = math.hypot(*(np.array(lm.to_xy(mission.dest_lon, mission.dest_lat))))
        margin = max(self.k.value("corridor_min_margin_m"), self.k.value("corridor_margin_fraction") * trip)

        cap = int(self.k.value("max_corridor_cells"))
        result, note = None, None
        for expansion in range(max_exp + 1):
            grid = self.rasters.window_grid(region.id, self._window(region, pts, margin * (2 ** expansion), lm))
            cells = grid.width * grid.height
            if cells > cap:                      # checked before any heavy calculation
                if result is None:
                    raise ApiError("ROUTE_TOO_LONG", "The trip is too long to calculate in one go; choose a closer destination",
                                   {"squares": cells, "limit": cap})
                note = "The corridor reached its size limit; a better route may exist further away"
                break
            result = self._run(region, mission, walker, res, scales, profiles, grid, stops, hz_warnings, refills,
                               lm, dust, extra_warnings, provider_warnings, pres)
            note = None
            if not result.touches_edge:
                break
            if expansion == max_exp:
                note = "A route still touches the edge of the widened corridor; a better route may exist further away"
        if note:
            for r in result.routes:
                r["warnings"].append(note)
        routes = self.routes.replace_all(mission_id, result.routes)
        return routes

    # ------------------------------------------------------------------ helpers
    def _check_points(self, mission, region) -> None:
        for name, lon, lat in (("start", mission.start_lon, mission.start_lat), ("dest", mission.dest_lon, mission.dest_lat)):
            if not region.contains(lon, lat):
                raise ApiError("OUT_OF_REGION", f"The {'start' if name == 'start' else 'destination'} is outside the region", {"field": name})
        if not region.routable_geometry:
            raise ApiError("DATA_NOT_PREPARED", "The routable area has not been prepared yet")
        for name, lon, lat in (("start", mission.start_lon, mission.start_lat), ("dest", mission.dest_lon, mission.dest_lat)):
            if not region.is_routable(lon, lat):
                raise ApiError("OUT_OF_COVERAGE", f"The {'start' if name == 'start' else 'destination'} is outside the area with full terrain data",
                               {"field": name})

    @staticmethod
    def _order_stops(stops, mission):
        """Visit science stops in the order of their position along the start-destination line."""
        lm = LocalMetric(mission.start_lon, mission.start_lat)
        ex, ey = lm.to_xy(mission.dest_lon, mission.dest_lat)
        norm = math.hypot(ex, ey) or 1.0
        return sorted(stops, key=lambda a: (float(np.dot(lm.to_xy(a.lon, a.lat), (ex, ey))) / norm, a.id))

    def _window(self, region, pts, margin_m, lm) -> BBox:
        xs, ys = zip(*[lm.to_xy(p[0], p[1]) for p in pts])
        w, s = lm.to_lonlat(min(xs) - margin_m, min(ys) - margin_m)
        e, n = lm.to_lonlat(max(xs) + margin_m, max(ys) + margin_m)
        box = BBox(float(w), float(s), float(e), float(n))
        rb = shape(region.routable_geometry).bounds
        clip = region.bbox.intersect(BBox(*rb))
        return box.intersect(clip) if clip else box

    def _apply_warnings(self, cat, hz_warnings, lm_grid):
        """User hazard warnings feed the same categories: HIGH = blocked core, MEDIUM = hazard_0_50, LOW = hazard_50_200."""
        extra_core = np.zeros(cat.bits.shape, bool)
        if not hz_warnings:
            return extra_core
        g = cat.grid
        rows, cols = np.mgrid[0:g.height, 0:g.width]
        lon, lat = g.rc_to_lonlat(rows, cols)
        keys = cat.category_keys
        for w in hz_warnings:
            lm = LocalMetric(w.lon, w.lat)
            x, y = lm.to_xy(lon, lat)
            inside = np.hypot(x, y) <= (w.radius_m or 0)
            if w.severity == "HIGH":
                extra_core |= inside
            else:
                key = "hazard_0_50" if w.severity == "MEDIUM" else "hazard_50_200"
                cat.bits[inside] |= np.uint32(1) << np.uint32(keys.index(key))
        return extra_core

    def _run(self, region, mission, walker, res, scales, profiles, grid, stops, hz_warnings, refills, lm,
             dust, extra_warnings, provider_warnings, pres):
        base = self.rasters.base_grid(region.id)
        cat = self.extractor.categories_at(region, grid)
        extra_core = self._apply_warnings(cat, hz_warnings, lm)

        # one cost call per calculation
        req = CostRequest(request_id=str(uuid.uuid4()), region_id=region.id, window=grid.bbox(), cell_size_m=grid.cell,
                          width=grid.width, height=grid.height, category_catalog_version=catalog_version(self.extractor.categories),
                          category_keys=cat.category_keys, category_bits=cat.bits, routable=cat.routable)
        cres = self.cost_chain.call("cost_factors", req, validate_args=(req,))
        factors = cres.value
        warnings = provider_warnings + [f"Cost provider: {s}; next provider used" for s in cres.skipped]

        blocked = routing.hard_mask(cat, self.k.value("max_slope_deg"), extra_core)
        o2_m, bat_m, _ = routing.resource_rates(cat, walker)
        usable_o2, usable_bat = res.usable_oxygen_kg(), res.usable_battery_wh()
        rc = lambda lon, lat: tuple(int(v) for v in grid.lonlat_to_rc(lon, lat))
        start, dest = rc(mission.start_lon, mission.start_lat), rc(mission.dest_lon, mission.dest_lat)
        stop_rc = [rc(a.lon, a.lat) for a in stops]
        used_stops = [a for a, p in zip(stops, stop_rc) if grid.inside(*p) and not blocked[p]]
        usable_stops = [p for p in stop_rc if grid.inside(*p) and not blocked[p]]
        if len(usable_stops) < len(stop_rc):
            extra_warnings = extra_warnings + [f"{len(stop_rc) - len(usable_stops)} science stop(s) on blocked ground "
                                               "(too steep, inside a hazard or a HIGH warning) were skipped"]
        waypoints = [start] + usable_stops + [dest]

        reason_all = None
        if blocked[start]:
            reason_all = "The start is on blocked ground (too steep, inside a hazard or outside the routable area)"
        elif blocked[dest]:
            reason_all = "The destination is on blocked ground (too steep, inside a hazard or outside the routable area)"

        refill_rc = {}
        for lon_, lat_, name in refills:
            p = rc(lon_, lat_)
            if grid.inside(*p) and not blocked[p]:
                refill_rc.setdefault(p, name)
        refill_mcp, refill_dist, blocked_rl = None, np.full(blocked.shape, np.inf), blocked
        if refill_rc and reason_all is None:
            ok, refill_mcp, refill_dist = routing.return_limit(o2_m, bat_m, blocked, start, list(refill_rc), usable_o2, usable_bat, grid.sampling)
            blocked_rl = blocked | ~ok

        share = routing.resource_share(o2_m, bat_m, walker, usable_o2, usable_bat)
        # near a terrain-class boundary (geologic-map offset) -> uncertain for dataConfidence
        code = cat.terrain_code
        edge = np.zeros(code.shape, bool)
        edge[:, 1:] |= (code[:, 1:] != code[:, :-1]) & (code[:, 1:] > 0) & (code[:, :-1] > 0)
        edge[1:, :] |= (code[1:, :] != code[:-1, :]) & (code[1:, :] > 0) & (code[:-1, :] > 0)
        near_boundary = (ndimage.distance_transform_edt(~edge, sampling=grid.sampling) < self.k.value("geology_offset_m")) if edge.any() \
            else np.zeros(code.shape, bool)

        hazard_shapes = [shape(f.geometry) for f in self.layers.get_features_by_type(region.id, "HAZARD")]
        bb = grid.bbox()
        science = [(shape(f.geometry), float(f.science_value or 0)) for f in self.layers.get_features_by_type(region.id, "SCIENCE_TARGET")
                   if bb.contains(*shape(f.geometry).centroid.coords[0])]

        costs, paths, reasons = {}, {}, {}
        open_edges = {"north": grid.y0 < base.y0 - 1e-6, "west": grid.x0 > base.x0 + 1e-6,
                      "south": (grid.y0 - grid.height * grid.cell) > (base.y0 - base.height * base.cell) + 1e-6,
                      "east": (grid.x0 + grid.width * grid.cell) < (base.x0 + base.width * base.cell) - 1e-6}
        rb = shape(region.routable_geometry).bounds   # do not widen past the routable area
        gb = grid.bbox()
        open_edges = {k_: v and {"north": gb.north < rb[3], "south": gb.south > rb[1], "west": gb.west > rb[0], "east": gb.east < rb[2]}[k_]
                      for k_, v in open_edges.items()}
        touches = False
        for t, prof in profiles.items():
            d = prof.distance_weight if prof.distance_weight is not None else scales.distance_weight
            E = routing.effective_log(factors.log_factors, routing.route_scales(prof, scales), {r.group: r for r in prof.rules},
                                      factors.hazard_floor)
            cost = routing.base_cost(d, share) * np.exp(E)
            costs[t] = cost
            reason = reason_all
            path, mask = None, blocked_rl
            if reason is None:
                path = routing.least_cost_path(cost, blocked_rl, waypoints, grid.sampling)
                if path is None:
                    mask = blocked
                    path = routing.least_cost_path(cost, blocked, waypoints, grid.sampling)
                    reason = "Beyond the oxygen and battery return limit" if path is not None else "No walkable path within the hard limits"
            if path is None:
                vertices = [start, dest] if start != dest else [start]
                if reason_all is None and any(open_edges.values()):
                    touches = True        # no path inside the corridor: widen it, a way around may lie outside
            else:
                if routing.touches_edge(path, cost.shape, open_edges):
                    touches = True
                # straighten the staircase: only shortcuts that cross no blocked square and cost no more; stops stay
                vertices = routing.smooth_path(path, cost, mask, grid.sampling, keep=frozenset(usable_stops))
            paths[t], reasons[t] = vertices, reason

        mp_cost = costs["MISSION_PRIORITY"]
        mp_best = routing.polyline_cost(mp_cost, paths["MISSION_PRIORITY"], grid.sampling) if reasons["MISSION_PRIORITY"] is None else None
        ctx = SimpleNamespace(cat=cat, grid=grid, walker=walker, resources=res, constants=self.k.value, near_boundary=near_boundary,
                              stops=used_stops, refill_mcp=refill_mcp, refill_dist=refill_dist,
                              refill_names={p: n for p, n in refill_rc.items()}, hazard_shapes=hazard_shapes, warnings=hz_warnings,
                              science=science, start_lonlat=(mission.start_lon, mission.start_lat),
                              dest_lonlat=(mission.dest_lon, mission.dest_lat), window=grid.bbox(), dust_status=dust,
                              extra_warnings=list(extra_warnings), o2_per_m=o2_m, blocked=blocked)
        now = now_iso()
        out = [evaluate(ctx, t, paths[t], mp_cost=mp_cost, mp_best=mp_best, provider_warnings=warnings,
                        cost_provider=cres.answered_by.as_dict(), priority_resolver=pres.answered_by.as_dict(),
                        cost_model_id=factors.cost_model_id, calculated_at=now, infeasible_reason=reasons[t]) for t in ROUTE_TYPES]
        return SimpleNamespace(routes=out, touches_edge=touches)
