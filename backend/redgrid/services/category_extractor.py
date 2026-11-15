"""CategoryExtractor (shared by the web app and the training package): categories of every square in a window.

Thresholds are planning constants, so a category means the same thing everywhere (RedGrid System Specification).
Distances (hazards, rims, science targets, rover path) are Euclidean distances in true ground metres on the
anisotropic routing grid (scipy distance_transform_edt with sampling = (dy, dx)). Features up to the largest buffer
outside the window are included by rasterising on a padded grid before cropping.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rasterio import features as rfeatures
from scipy import ndimage
from shapely.geometry import mapping, shape

from ..enums import TERRAIN_CODES
from ..geo import GridSpec, lonlat_to_eqc, map_geometry

TERRAIN_BITS = {"REGOLITH": "terrain_regolith", "BEDROCK": "terrain_bedrock", "SAND": "terrain_sand", "BOULDER_FIELD": "terrain_boulder"}
TERRAIN_FACTOR_KEYS = {"REGOLITH": "terrain_factor_regolith", "BEDROCK": "terrain_factor_bedrock",
                       "SAND": "terrain_factor_sand", "BOULDER_FIELD": "terrain_factor_boulder"}


@dataclass
class CategoryGrid:
    grid: GridSpec
    category_keys: list[str]
    bits: np.ndarray            # uint32
    slope_deg: np.ndarray       # float, NaN = no data
    elevation_m: np.ndarray
    roughness_m: np.ndarray
    terrain_code: np.ndarray    # 0 = no data, 1..4
    terrain_factor: np.ndarray  # energy factor vs regolith (NaN where no data)
    routable: np.ndarray        # bool: inside routable area and every routing layer has a value
    hazard_core: np.ndarray     # bool: inside a hazard polygon (blocked)
    no_comm: np.ndarray         # bool
    near_science: np.ndarray    # bool

    def has(self, key: str) -> np.ndarray:
        b = self.category_keys.index(key)
        return ((self.bits >> np.uint32(b)) & np.uint32(1)).astype(bool)


def _to_eqc(geom: dict):
    return map_geometry(shape(geom), lonlat_to_eqc)


class CategoryExtractor:
    def __init__(self, rasters, layers, cost_models, constants):
        self.rasters = rasters
        self.layers = layers
        self.cost_models = cost_models
        self.constants = constants
        self.categories = cost_models.get_categories()            # bit order
        self.keys = [c.key for c in self.categories]
        if [c.bit for c in self.categories] != list(range(len(self.categories))):
            raise RuntimeError("category bits must be 0..N-1 without gaps")

    def _bit(self, key: str) -> np.uint32:
        return np.uint32(1) << np.uint32(self.keys.index(key))

    def _distance(self, region, grid: GridSpec, feature_type: str, max_d: float) -> tuple[np.ndarray, np.ndarray]:
        """(distance in ground metres to the nearest feature, inside mask) on the window grid."""
        feats = self.layers.get_features_by_type(region.id, feature_type)
        H, W = grid.height, grid.width
        if not feats:
            return np.full((H, W), np.inf), np.zeros((H, W), bool)
        pad = int(np.ceil(max_d / min(grid.dx_ground, grid.dy_ground))) + 2
        pg = GridSpec(x0=grid.x0 - pad * grid.cell, y0=grid.y0 + pad * grid.cell, cell=grid.cell, width=W + 2 * pad, height=H + 2 * pad)
        shapes = [(mapping(_to_eqc(f.geometry)), 1) for f in feats]
        mask = rfeatures.rasterize(shapes, out_shape=(pg.height, pg.width), transform=pg.affine(), all_touched=True, fill=0,
                                   dtype="uint8").astype(bool)
        if not mask.any():
            return np.full((H, W), np.inf), np.zeros((H, W), bool)
        d = ndimage.distance_transform_edt(~mask, sampling=pg.sampling)
        inside = mask
        if feature_type == "HAZARD":   # polygons: 'inside' means the centre is inside, not just touched
            inside = rfeatures.rasterize(shapes, out_shape=(pg.height, pg.width), transform=pg.affine(), all_touched=False,
                                         fill=0, dtype="uint8").astype(bool)
        return d[pad:pad + H, pad:pad + W], inside[pad:pad + H, pad:pad + W]

    def categories_at(self, region, grid: GridSpec) -> CategoryGrid:
        c = self.constants.value
        rid = region.id
        slope = self.rasters.load_window(rid, "slope", grid)
        rough = self.rasters.load_window(rid, "roughness", grid)
        tclass = np.nan_to_num(self.rasters.load_window(rid, "terrain_class", grid), nan=0).astype(np.uint8)
        elev = self.rasters.load_window(rid, "elevation", grid)
        comm = self.rasters.load_window(rid, "comm_coverage", grid) if self.rasters.has(rid, "comm_coverage") \
            else np.full(slope.shape, np.nan)

        H, W = grid.height, grid.width
        bits = np.zeros((H, W), np.uint32)
        # slope bands (deg); squares above max_slope_deg also carry slope_15_20 but are blocked by the hard mask
        bands = [("slope_0_5", 0, 5), ("slope_5_10", 5, 10), ("slope_10_15", 10, 15), ("slope_15_20", 15, np.inf)]
        for key, lo, hi in bands:
            bits[(slope >= lo) & (slope < hi)] |= self._bit(key)
        smooth, high = c("rough_smooth_max_m"), c("rough_high_min_m")
        bits[rough < smooth] |= self._bit("rough_low")
        bits[(rough >= smooth) & (rough < high)] |= self._bit("rough_medium")
        bits[rough >= high] |= self._bit("rough_high")
        tfactor = np.full((H, W), np.nan)
        for code, name in TERRAIN_CODES.items():
            m = tclass == code
            bits[m] |= self._bit(TERRAIN_BITS[name])
            tfactor[m] = c(TERRAIN_FACTOR_KEYS[name])

        near, far = c("hazard_near_m"), c("hazard_far_m")
        dh, core = self._distance(region, grid, "HAZARD", far)
        bits[(~core) & (dh < near)] |= self._bit("hazard_0_50")
        bits[(dh >= near) & (dh < far)] |= self._bit("hazard_50_200")
        dr, _ = self._distance(region, grid, "RIM_SCARP", c("rim_buffer_m"))
        bits[dr < c("rim_buffer_m")] |= self._bit("near_rim_scarp")
        ds_, _ = self._distance(region, grid, "SCIENCE_TARGET", c("science_buffer_m"))
        near_sci = ds_ < c("science_buffer_m")
        bits[near_sci] |= self._bit("near_science")
        dp, _ = self._distance(region, grid, "ROVER_PATH", c("rover_path_buffer_m"))
        bits[dp < c("rover_path_buffer_m")] |= self._bit("near_rover_path")
        no_comm = ~(comm == 1)          # no value counts as no coverage (never assumed covered)
        bits[no_comm] |= self._bit("no_comm")

        have_all = np.isfinite(slope) & np.isfinite(rough) & (tclass > 0) & np.isfinite(elev)
        bits[~have_all] |= self._bit("data_missing")
        inside = np.zeros((H, W), bool)
        if region.routable_geometry:
            inside = rfeatures.rasterize([(mapping(_to_eqc(region.routable_geometry)), 1)], out_shape=(H, W),
                                         transform=grid.affine(), all_touched=False, fill=0, dtype="uint8").astype(bool)
        return CategoryGrid(grid=grid, category_keys=list(self.keys), bits=bits, slope_deg=slope, elevation_m=elev,
                            roughness_m=rough, terrain_code=tclass, terrain_factor=tfactor, routable=inside & have_all,
                            hazard_core=core, no_comm=no_comm, near_science=near_sci)

    def categories_at_point(self, region, lon: float, lat: float) -> tuple[list, dict]:
        """Categories at one point plus the raw values there (for LocationInfo)."""
        base = self.rasters.base_grid(region.id)
        row, col = base.lonlat_to_rc(lon, lat)
        row, col = int(row), int(col)
        if not base.inside(row, col):
            return [], {}
        g = GridSpec(x0=base.x0 + (col - 1) * base.cell, y0=base.y0 - (row - 1) * base.cell, cell=base.cell, width=3, height=3)
        cg = self.categories_at(region, g)
        bits = int(cg.bits[1, 1])
        cats = [cat for cat in self.categories if bits >> cat.bit & 1]
        code = int(cg.terrain_code[1, 1])
        values = {"slope": cg.slope_deg[1, 1], "roughness": cg.roughness_m[1, 1], "elevation": cg.elevation_m[1, 1],
                  "terrain_class": TERRAIN_CODES.get(code), "routable": bool(cg.routable[1, 1])}
        return cats, values
