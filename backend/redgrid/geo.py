"""Coordinates.

Data system (Mars 2020 TRN products and every prepared routing raster): Mars 2000 sphere, R = 3 396 190 m,
equirectangular with standard parallel 0 deg and central meridian 0 deg:  x = R*lon,  y = R*lat  (radians).

Important: with standard parallel 0, projected metres are true only north-south. East-west, one projected
metre is cos(lat) metres on the ground (0.9486 at Jezero, 18.44 N). An "8 m" cell is therefore 8 m N-S by
7.59 m E-W. Every slope, distance, energy and path length in this backend uses the true ground spacing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

R_MARS = 3_396_190.0  # Mars 2000 IAU sphere radius, m
PROJ4 = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"


def lonlat_to_eqc(lon, lat):
    return R_MARS * np.radians(lon), R_MARS * np.radians(lat)


def eqc_to_lonlat(x, y):
    return np.degrees(np.asarray(x) / R_MARS), np.degrees(np.asarray(y) / R_MARS)


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_dict(self) -> dict:
        return {"west": round(self.west, 6), "south": round(self.south, 6),
                "east": round(self.east, 6), "north": round(self.north, 6)}

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def intersect(self, other: "BBox") -> "BBox | None":
        w, s, e, n = max(self.west, other.west), max(self.south, other.south), min(self.east, other.east), min(self.north, other.north)
        return BBox(w, s, e, n) if w < e and s < n else None


class LocalMetric:
    """Local tangent-plane metres around (lon0, lat0) for distances between features (error < 0.1 % over 30 km)."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = R_MARS * math.cos(math.radians(lat0)) * math.pi / 180.0
        self.ky = R_MARS * math.pi / 180.0

    def to_xy(self, lon, lat):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky

    def to_lonlat(self, x, y):
        return np.asarray(x) / self.kx + self.lon0, np.asarray(y) / self.ky + self.lat0


@dataclass(frozen=True)
class GridSpec:
    """A window of the routing grid. Row 0 is the northern edge; (x0, y0) is the north-west corner in eqc metres."""
    x0: float
    y0: float
    cell: float          # projected cell size (8 m)
    width: int
    height: int

    @property
    def center_lat(self) -> float:
        return float(np.degrees((self.y0 - self.cell * self.height / 2) / R_MARS))

    @property
    def dx_ground(self) -> float:
        """East-west ground size of a cell (m)."""
        return self.cell * math.cos(math.radians(self.center_lat))

    @property
    def dy_ground(self) -> float:
        return self.cell

    @property
    def sampling(self) -> tuple[float, float]:
        """(row spacing, column spacing) in ground metres, for scikit-image and scipy."""
        return (self.dy_ground, self.dx_ground)

    def bbox(self) -> BBox:
        w, n = eqc_to_lonlat(self.x0, self.y0)
        e, s = eqc_to_lonlat(self.x0 + self.cell * self.width, self.y0 - self.cell * self.height)
        return BBox(float(w), float(s), float(e), float(n))

    def lonlat_to_rc(self, lon, lat):
        x, y = lonlat_to_eqc(lon, lat)
        col = np.floor((x - self.x0) / self.cell).astype(int)
        row = np.floor((self.y0 - y) / self.cell).astype(int)
        return row, col

    def rc_to_lonlat(self, row, col):
        x = self.x0 + (np.asarray(col) + 0.5) * self.cell
        y = self.y0 - (np.asarray(row) + 0.5) * self.cell
        return eqc_to_lonlat(x, y)

    def inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def affine(self):
        from rasterio.transform import Affine
        return Affine(self.cell, 0, self.x0, 0, -self.cell, self.y0)


def map_geometry(geom, fn):
    """Apply fn(x_array, y_array) -> (x_array, y_array) to every coordinate of a shapely geometry."""
    import shapely

    def _f(arr):
        x, y = fn(arr[:, 0], arr[:, 1])
        return np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    return shapely.transform(geom, _f)
