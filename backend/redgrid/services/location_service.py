"""LocationService: everything shown when the user clicks one point (2D or 3D)."""
from __future__ import annotations

import numpy as np
from shapely.geometry import Point, shape

from .. import serialize as S
from ..errors import ApiError
from ..geo import LocalMetric, map_geometry
from .evaluation import dust_status


def environment_json(environment, region_id: int) -> dict:
    snap = environment.get_snapshot(region_id) or {}
    win = environment.get_demo_window()
    has = snap.get("observed_at") is not None
    r = lambda v, n=1: None if v is None else round(float(v), n)
    return {"regionId": region_id, "temperature": r(snap.get("temperature")), "pressure": r(snap.get("pressure")),
            "windSpeed": r(snap.get("wind_speed")), "dustStatus": dust_status(snap.get("dust_opacity")),
            "solsWithData": snap.get("sols_with_data") or 0,
            "window": None if not win else {"startSol": win["start_sol"], "endSol": win["end_sol"]},
            "observedAt": snap.get("observed_at"), "dataState": snap.get("data_state") if has else "DATA_UNAVAILABLE",
            "source": snap.get("source")}


class LocationService:
    def __init__(self, *, regions, layers, rasters, environment, extractor):
        self.regions, self.layers, self.rasters, self.environment, self.extractor = regions, layers, rasters, environment, extractor

    def _nearest(self, region_id, ftype, lon, lat, refill_only=False):
        feats = self.layers.get_features_by_type(region_id, ftype)
        if refill_only:
            feats = [f for f in feats if f.provides_refill]
        if not feats:
            return None, None
        lm = LocalMetric(lon, lat)
        p = Point(0, 0)
        best = min(((p.distance(map_geometry(shape(f.geometry), lm.to_xy)), f) for f in feats),
                   key=lambda t: t[0])
        return best[1], round(best[0], 1)

    def location(self, region_id: int, lon: float, lat: float) -> dict:
        region = self.regions.get_by_id(region_id)
        if not region.contains(lon, lat):
            raise ApiError("OUT_OF_REGION", "The point is outside the region", {"lon": lon, "lat": lat})
        cats, vals = [], {}
        if self.rasters.has(region_id, "slope"):
            cats, vals = self.extractor.categories_at_point(region, lon, lat)
        routable = bool(vals.get("routable")) and region.is_routable(lon, lat)
        num = lambda v, n=2: None if v is None or not np.isfinite(v) else round(float(v), n)
        units = [f for f in self.layers.get_features_by_type(region_id, "TERRAIN_UNIT") if shape(f.geometry).covers(Point(lon, lat))]
        hz, dhz = self._nearest(region_id, "HAZARD", lon, lat)
        sc, dsc = self._nearest(region_id, "SCIENCE_TARGET", lon, lat)
        sp, dsp = self._nearest(region_id, "SAFE_POINT", lon, lat)
        rp, drp = self._nearest(region_id, "SAFE_POINT", lon, lat, refill_only=True)
        elev = vals.get("elevation")
        state = "DERIVED" if routable else ("LIMITED_CONFIDENCE" if elev is not None and np.isfinite(elev) else "DATA_UNAVAILABLE")
        quality = "High" if routable else ("Limited" if state == "LIMITED_CONFIDENCE" else "Unavailable")
        return {
            "lon": lon, "lat": lat, "routable": routable,
            "elevationM": num(elev), "slopeDeg": num(vals.get("slope")) if routable else None,
            "roughnessM": num(vals.get("roughness"), 3) if routable else None,
            "terrainUnit": units[0].name if units else None,
            "terrainClass": vals.get("terrain_class") if routable else None,
            "terrainClassDataState": "LIMITED_CONFIDENCE",
            "categories": [S.category_ref(c) for c in cats] if routable else [],
            "nearestHazard": S.feature_ref(hz), "nearestScienceTarget": S.feature_ref(sc),
            "nearestSafePoint": S.feature_ref(sp), "nearestRefillPoint": S.feature_ref(rp),
            "distanceToNearestHazardM": dhz, "distanceToNearestScienceTargetM": dsc,
            "distanceToNearestSafePointM": dsp, "distanceToNearestRefillPointM": drp,
            "environment": environment_json(self.environment, region_id),
            "dataState": state, "dataQuality": quality,
        }
