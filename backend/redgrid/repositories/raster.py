"""Reads the prepared GeoTIFFs (prepared-data contract). Never derives or changes data."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

from ..errors import ApiError
from ..geo import BBox, GridSpec, lonlat_to_eqc

ROUTING_LAYERS = ("elevation", "slope", "roughness", "terrain_class", "comm_coverage")


class RasterRepository:
    def __init__(self, data_dir: str, layers):
        self.data_dir = Path(data_dir)
        self.layers = layers          # LayerRepository

    def path(self, region_id: int, layer_key: str) -> Path:
        layer = self.layers.get_by_key(region_id, layer_key)
        if layer.kind != "RASTER":
            raise ApiError("LAYER_NOT_RASTER", f"Layer '{layer_key}' is not a raster layer")
        p = self.data_dir / layer.raster_path
        if not p.exists():
            raise ApiError("DATA_NOT_PREPARED", f"Prepared file for layer '{layer_key}' is missing ({layer.raster_path})")
        return p

    def has(self, region_id: int, layer_key: str) -> bool:
        try:
            self.path(region_id, layer_key)
            return True
        except ApiError:
            return False

    def base_grid(self, region_id: int) -> GridSpec:
        """The routing grid of the whole prepared area (from slope.tif)."""
        with rasterio.open(self.path(region_id, "slope")) as ds:
            t = ds.transform
            return GridSpec(x0=t.c, y0=t.f, cell=t.a, width=ds.width, height=ds.height)

    def window_grid(self, region_id: int, bbox: BBox) -> GridSpec:
        """Snap a lon/lat box to the routing grid, clipped to the prepared area."""
        base = self.base_grid(region_id)
        x0, y1 = lonlat_to_eqc(bbox.west, bbox.north)
        x1, y0 = lonlat_to_eqc(bbox.east, bbox.south)
        c0 = max(0, int(np.floor((x0 - base.x0) / base.cell)))
        c1 = min(base.width, int(np.ceil((x1 - base.x0) / base.cell)))
        r0 = max(0, int(np.floor((base.y0 - y1) / base.cell)))
        r1 = min(base.height, int(np.ceil((base.y0 - y0) / base.cell)))
        if c1 - c0 < 2 or r1 - r0 < 2:
            raise ApiError("OUT_OF_COVERAGE", "The requested area is outside the prepared terrain data")
        return GridSpec(x0=base.x0 + c0 * base.cell, y0=base.y0 - r0 * base.cell, cell=base.cell, width=c1 - c0, height=r1 - r0)

    def load_window(self, region_id: int, layer_key: str, grid: GridSpec) -> np.ndarray:
        """Values on exactly this grid window (float64, NaN where there is no data or outside the file)."""
        with rasterio.open(self.path(region_id, layer_key)) as ds:
            t = ds.transform
            col = int(round((grid.x0 - t.c) / t.a))
            row = int(round((t.f - grid.y0) / -t.e))
            if abs(t.a - grid.cell) > 1e-6:
                raise ApiError("DATA_NOT_PREPARED", f"Layer '{layer_key}' is not on the routing grid")
            a = ds.read(1, window=Window(col, row, grid.width, grid.height), boundless=True,
                        fill_value=ds.nodata if ds.nodata is not None else 0).astype("float64")
            if ds.nodata is not None:
                a[a == ds.nodata] = np.nan
            return a

    def sample(self, region_id: int, layer_key: str, lon: float, lat: float) -> float | None:
        with rasterio.open(self.path(region_id, layer_key)) as ds:
            x, y = lonlat_to_eqc(lon, lat)
            row, col = ds.index(float(x), float(y))
            if not (0 <= row < ds.height and 0 <= col < ds.width):
                return None
            v = ds.read(1, window=Window(col, row, 1, 1))[0, 0]
            if ds.nodata is not None and v == ds.nodata:
                return None
            v = float(v)
            return None if np.isnan(v) else v

    def load_preview(self, region_id: int, layer_key: str, bbox: BBox, max_size: int, categorical: bool = False):
        """Downsampled values over a lon/lat box (3D terrain and overlays). Returns (array, GridSpec-like bounds)."""
        p = self.path(region_id, layer_key)
        with rasterio.open(p) as ds:
            x0, y1 = lonlat_to_eqc(bbox.west, bbox.north)
            x1, y0 = lonlat_to_eqc(bbox.east, bbox.south)
            win = rasterio.windows.from_bounds(float(x0), float(y0), float(x1), float(y1), transform=ds.transform)
            scale = max(win.width, win.height) / max_size
            out_w = max(2, int(round(win.width / max(scale, 1e-9)))) if scale > 1 else max(2, int(round(win.width)))
            out_h = max(2, int(round(win.height / max(scale, 1e-9)))) if scale > 1 else max(2, int(round(win.height)))
            out_w, out_h = min(out_w, max_size), min(out_h, max_size)
            a = ds.read(1, window=win, out_shape=(out_h, out_w), boundless=True,
                        fill_value=ds.nodata if ds.nodata is not None else 0,
                        resampling=Resampling.nearest if categorical else Resampling.average).astype("float64")
            if ds.nodata is not None:
                a[a == ds.nodata] = np.nan
            return a
