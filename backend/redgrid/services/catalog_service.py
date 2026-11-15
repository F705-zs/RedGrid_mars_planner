"""CatalogService: regions, layers, presets, categories, weights, constants, demo window, providers, terrain for 3D."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .. import serialize as S
from ..errors import ApiError, validation
from ..geo import BBox, R_MARS

# Display colours (colour-blind-safe where categorical; Okabe-Ito for terrain classes)
TERRAIN_RGB = {1: (204, 121, 167), 2: (86, 180, 233), 3: (230, 159, 0), 4: (213, 94, 0)}


class CatalogService:
    def __init__(self, *, regions, datasets, layers, rasters, profiles, presets, terrain_classes, cost_models, constants,
                 environment, chains):
        self.regions, self.datasets, self.layers, self.rasters = regions, datasets, layers, rasters
        self.profiles, self.presets, self.terrain_classes = profiles, presets, terrain_classes
        self.cost_models, self.k, self.environment, self.chains = cost_models, constants, environment, chains

    def regions_json(self):
        return [S.region(r) for r in self.regions.get_all()]

    def region_json(self, rid):
        return S.region(self.regions.get_by_id(rid))

    def layers_json(self, rid):
        self.regions.get_by_id(rid)
        return [S.layer(l) for l in self.layers.get_by_region(rid)]

    def layer_geojson(self, rid, key):
        self.regions.get_by_id(rid)
        return {"type": "FeatureCollection", "features": [S.feature_geojson(f) for f in self.layers.get_features(rid, key)]}

    def datasets_json(self, rid):
        self.regions.get_by_id(rid)
        return [S.dataset(d) for d in self.datasets.get_by_region(rid)]

    def route_profiles_json(self):
        return [S.route_profile(p) for p in self.profiles.get_all()]

    def presets_json(self):
        return [S.preset(p) for p in self.presets.get_all()]

    def categories_json(self):
        return [S.category(c) for c in self.cost_models.get_categories()]

    def terrain_mapping_json(self):
        rows = self.terrain_classes.get_all()
        cache = {}
        out = []
        for r in rows:
            ds = cache.setdefault(r["dataset_id"], self.datasets.get_by_id(r["dataset_id"]))
            out.append(S.terrain_mapping(r, ds))
        return out

    def active_cost_model_json(self):
        m = self.cost_models.get_active()
        return S.cost_model(m, self.datasets.get_training_sources(m.id))

    def cost_models_json(self):
        return [S.cost_model(m, with_weights=False) for m in self.cost_models.get_all()]

    def cost_model_json(self, mid):
        m = self.cost_models.get_by_id(mid)
        return S.cost_model(m, self.datasets.get_training_sources(m.id))

    def constants_json(self):
        return [S.constant(c) for c in self.k.get_all()]

    def demo_window_json(self):
        return S.demo_window(self.environment.get_demo_window())

    def providers_json(self):
        cost, prio, res = self.chains
        return {"cost": cost.statuses(), "priority": prio.statuses(), "resource": res.statuses()}

    # ------------------------------------------------------------ 3D terrain and textures
    def _bbox(self, region, args) -> BBox:
        keys = ("west", "south", "east", "north")
        if all(args.get(k) in (None, "") for k in keys):
            return region.bbox
        try:
            b = BBox(*[float(args[k]) for k in keys])
        except (KeyError, TypeError, ValueError):
            raise validation("west, south, east and north must all be numbers")
        if not (b.west < b.east and b.south < b.north):
            raise validation("bbox is empty")
        if b.intersect(region.bbox) != b:
            raise ApiError("OUT_OF_REGION", "The bbox leaves the region")
        return b

    def terrain(self, rid, args):
        region = self.regions.get_by_id(rid)
        try:
            max_size = int(args.get("maxSize", 256))
        except ValueError:
            raise validation("maxSize must be a whole number", field="maxSize")
        if not 16 <= max_size <= 512:
            raise validation("maxSize must be from 16 to 512", field="maxSize")
        b = self._bbox(region, args)
        a = self.rasters.load_preview(rid, "elevation", b, max_size)
        h, w = a.shape
        cell = (b.north - b.south) * np.pi / 180 * R_MARS / h
        layer = self.layers.get_by_key(rid, "elevation")
        finite = a[np.isfinite(a)]
        return {"regionId": rid, "bbox": b.as_dict(), "width": int(w), "height": int(h), "cellSizeM": round(float(cell), 2),
                "minElevationM": round(float(finite.min()), 2) if finite.size else None,
                "maxElevationM": round(float(finite.max()), 2) if finite.size else None,
                "elevations": [None if not np.isfinite(v) else round(float(v), 2) for v in a.ravel()],
                "dataState": layer.data_state if finite.size else "DATA_UNAVAILABLE", "dataset": S.dataset_ref(layer.dataset)}

    def texture(self, rid, args) -> bytes:
        region = self.regions.get_by_id(rid)
        key = args.get("layer", "hillshade")
        layer = self.layers.get_by_key(rid, key)
        if layer.kind != "RASTER":
            raise ApiError("LAYER_NOT_RASTER", f"Layer '{key}' is not a raster layer")
        try:
            size = int(args.get("size", 1024))
        except ValueError:
            raise validation("size must be a whole number", field="size")
        if not 256 <= size <= 2048:
            raise validation("size must be from 256 to 2048", field="size")
        b = self._bbox(region, args)
        categorical = key in ("terrain_class", "comm_coverage")
        a = self.rasters.load_preview(rid, key, b, size, categorical=categorical)
        rgba = np.zeros(a.shape + (4,), np.uint8)
        ok = np.isfinite(a)
        if key == "terrain_class":
            for code, rgb in TERRAIN_RGB.items():
                m = a == code
                rgba[m, :3], rgba[m, 3] = rgb, 255
        elif key == "comm_coverage":
            rgba[a == 1] = (0, 158, 115, 140)
            rgba[a == 0] = (90, 90, 90, 140)
        else:
            if key == "slope":
                lo, hi = 0.0, float(self.k.value("max_slope_deg"))
            elif ok.any():
                lo, hi = np.nanpercentile(a, 1), np.nanpercentile(a, 99)
            else:
                lo, hi = 0.0, 1.0
            v = np.clip((np.nan_to_num(a, nan=lo) - lo) / max(hi - lo, 1e-9), 0, 1)
            g = (v * 255).astype(np.uint8)
            rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = g
            rgba[..., 3] = np.where(ok, 255, 0)
        # missing data is never smoothed over: transparent cells, drawn grey by the client
        buf = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
        return buf.getvalue()
