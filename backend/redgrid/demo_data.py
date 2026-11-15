"""SYNTHETIC prepared data for development and frontend integration (every layer labelled DEMONSTRATION_DATA).

The terrain, roughness, terrain classes, hazards and rims are generated (fractal terrain plus a delta-front-like
scarp). Real positions are used where we have them: the landing site (Ares Base One), the comms tower, the
Perseverance traverse and the Three Forks depot (both from the 3D repo's MMGIS-derived traverse, sols 14-2022).
The files follow the prepared-data contract exactly, so the real data tool's output is a drop-in replacement.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio import features as rfeatures
from rasterio.crs import CRS
from scipy import ndimage
from shapely.geometry import LineString, mapping, shape

from .geo import PROJ4, R_MARS, eqc_to_lonlat, lonlat_to_eqc, map_geometry

LANDING = (77.45088573, 18.44462715, -2569.9)     # lon, lat, elevation (3D repo meta.json, HiRISE)
CELL = 8.0
BOX_M = (-7000.0, 3000.0, -3000.0, 4000.0)        # west, east, south, north in metres from the landing site
TRAVERSE = Path(__file__).parent / "demo_traverse.json"


def _local_to_lonlat(x, north):
    lon0, lat0, _ = LANDING
    return lon0 + np.degrees(np.asarray(x) / (R_MARS * math.cos(math.radians(lat0)))), lat0 + np.degrees(np.asarray(north) / R_MARS)


def _fractal(shape_, beta, rng):
    h, w = shape_
    k = np.fft.fftfreq(h)[:, None]
    l = np.fft.fftfreq(w)[None, :]
    f = np.sqrt(k * k + l * l)
    f[0, 0] = 1.0
    z = np.real(np.fft.ifft2((rng.normal(size=shape_) + 1j * rng.normal(size=shape_)) / f ** beta))
    return (z - z.mean()) / z.std()


def _horn_slope(z, dx, dy):
    p = np.pad(z, 1, mode="edge")
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * dy)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def _hillshade(z, dx, dy, az=315.0, alt=45.0):
    gy, gx = np.gradient(z, dy, dx)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    zen, azr = math.radians(90 - alt), math.radians(az)
    hs = math.cos(zen) * np.cos(slope) + math.sin(zen) * np.sin(slope) * np.cos(azr - aspect)
    return np.clip(hs * 255, 0, 254).astype(np.uint8)


def _viewshed(z, dx, dy, tower_rc, mast, receiver, factor=4, n=220):
    """Line of sight from the mast top to a suit antenna, on a coarser grid, with Mars curvature (drop = d^2 / 2R)."""
    zc = z[::factor, ::factor]
    H, W = zc.shape
    tr, tc = tower_rc[0] / factor, tower_rc[1] / factor
    zt = ndimage.map_coordinates(zc, [[tr], [tc]], order=1)[0] + mast
    rr, cc = np.mgrid[0:H, 0:W].astype(float)
    target = zc + receiver
    vis = np.ones((H, W), bool)
    for t in np.linspace(0.02, 0.98, n):
        r, c = tr + t * (rr - tr), tc + t * (cc - tc)
        ground = ndimage.map_coordinates(zc, [r.ravel(), c.ravel()], order=1).reshape(H, W)
        dist = np.hypot((r - tr) * dy * factor, (c - tc) * dx * factor)
        drop = dist ** 2 / (2 * R_MARS)
        line = zt + t * (target - zt)
        vis &= line >= ground - drop
    up = np.kron(vis, np.ones((factor, factor), bool))[: z.shape[0], : z.shape[1]]
    return up


def _polys(mask, transform, min_area_m2, coslat):
    out = []
    for geom, val in rfeatures.shapes(mask.astype(np.uint8), mask=mask, transform=transform):
        g = shape(geom)
        if g.area * coslat >= min_area_m2:
            out.append(map_geometry(g, eqc_to_lonlat))
    return out


def _write(path, arr, transform, nodata, dtype):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype,
                       crs=CRS.from_proj4(PROJ4), transform=transform, nodata=nodata, tiled=True, compress="deflate",
                       blockxsize=256, blockysize=256) as ds:
        ds.write(arr.astype(dtype), 1)


def make_demo(data_dir: str, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    out = Path(data_dir) / "jezero"
    (out / "vectors").mkdir(parents=True, exist_ok=True)
    (out / "meda").mkdir(parents=True, exist_ok=True)
    lon0, lat0, z0 = LANDING
    coslat = math.cos(math.radians(lat0))
    (w_lon, s_lat), (e_lon, n_lat) = _local_to_lonlat(BOX_M[0], BOX_M[2]), _local_to_lonlat(BOX_M[1], BOX_M[3])
    x0, y1 = lonlat_to_eqc(w_lon, n_lat)
    x1, y0 = lonlat_to_eqc(e_lon, s_lat)
    x0, y1 = math.floor(x0 / CELL) * CELL, math.ceil(y1 / CELL) * CELL
    W, H = int(math.ceil((x1 - x0) / CELL)), int(math.ceil((y1 - y0) / CELL))
    transform = rasterio.transform.Affine(CELL, 0, x0, 0, -CELL, y1)
    dx, dy = CELL * coslat, CELL

    rows, cols = np.mgrid[0:H, 0:W]
    xs = x0 + (cols + 0.5) * CELL
    ys = y1 - (rows + 0.5) * CELL
    lon, lat = eqc_to_lonlat(xs, ys)
    east = np.radians(lon - lon0) * R_MARS * coslat
    north = np.radians(lat - lat0) * R_MARS
    # synthetic relief: regional tilt + fractal hills + a delta-front-like scarp ~4.5 km west of the landing site
    z = z0 + 0.004 * north - 0.002 * east + 22 * _fractal((H, W), 2.4, rng) + 3 * _fractal((H, W), 1.7, rng)
    # delta-front-like scarp ~4.5 km west of the landing site: up to ~70 m high with walls to ~30 deg, cut by
    # low-relief ramps (as real delta fronts are cut by channels), so the upper surface can be reached
    scarp_h = 70.0 * (0.25 + 0.75 * (0.5 + 0.5 * np.sin(north / 1100.0 + 1.0)))
    z += scarp_h / (1 + np.exp((east + 4500 + 300 * np.sin(north / 900)) / 30.0))
    # small impact craters: depth 0.2-0.25 of the radius (depth/diameter 0.10-0.125, moderately degraded; fresh simple
    # craters reach about 0.2, Pike 1977) with a raised rim
    for _ in range(9):
        cx, cy = rng.uniform(BOX_M[0] + 800, BOX_M[1] - 800), rng.uniform(BOX_M[2] + 800, BOX_M[3] - 800)
        if math.hypot(cx, cy) < 700:          # keep the landing site clear
            continue
        R = rng.uniform(90, 260)
        r = np.hypot(east - cx, north - cy) / R
        depth = rng.uniform(0.2, 0.25) * R
        bowl = np.where(r < 1, depth * (r ** 2 - 1), 0.0)
        rim = 0.04 * R * np.exp(-((r - 1) / 0.25) ** 2)
        z += bowl + rim
    slope = _horn_slope(z, dx, dy)
    rough_noise = _fractal((H, W), 1.8, rng)
    rough = np.exp(-1.95 + 0.7 * rough_noise) + 0.025 * slope        # metres; rougher on slopes
    tnoise, snoise = _fractal((H, W), 2.2, rng), _fractal((H, W), 2.0, rng)
    tclass = np.full((H, W), 1, np.uint8)                            # regolith
    tclass[tnoise > 0.6] = 2                                         # bedrock patches
    tclass[(snoise > 1.0) & (slope < 8)] = 3                         # sand in low, gentle ground
    tclass[(slope > 14) & (rough > 0.5)] = 4                         # blocky ground on steep rough slopes
    rough[tclass == 4] *= 1.6

    tower = (lon0 - 26 / (R_MARS * coslat) * 180 / math.pi, lat0 + 10 / R_MARS * 180 / math.pi)
    tx, ty = lonlat_to_eqc(*tower)
    tower_rc = ((y1 - ty) / CELL, (tx - x0) / CELL)
    comm = _viewshed(z, dx, dy, tower_rc, mast=18.0, receiver=2.0).astype(np.uint8)

    _write(out / "elevation.tif", z, transform, -9999.0, "float32")
    _write(out / "slope.tif", slope, transform, -9999.0, "float32")
    _write(out / "roughness.tif", rough, transform, -9999.0, "float32")
    _write(out / "terrain_class.tif", tclass, transform, 255, "uint8")
    _write(out / "comm_coverage.tif", comm, transform, 255, "uint8")
    _write(out / "hillshade.tif", _hillshade(z, dx, dy), transform, 255, "uint8")

    def fc(feats):
        return {"type": "FeatureCollection", "features": feats}

    hazards = _polys(ndimage.binary_opening(rough >= 1.0), transform, 192.0, coslat)
    (out / "vectors" / "hazards.geojson").write_text(json.dumps(fc([
        {"type": "Feature", "geometry": mapping(g), "properties": {"name": f"Rough ground {i + 1} (synthetic)"}} for i, g in enumerate(hazards)])))
    rims = []
    for g in _polys(slope >= 25.0, transform, 0.0, coslat):
        for ring in ([g.exterior] if g.geom_type == "Polygon" else [p.exterior for p in g.geoms]):
            ln = LineString(ring.coords)
            xy = map_geometry(ln, lambda x, y: (np.radians(x - lon0) * R_MARS * coslat, np.radians(y - lat0) * R_MARS))
            if xy.length >= 50.0:
                rims.append(ln)
    (out / "vectors" / "rim_scarps.geojson").write_text(json.dumps(fc([
        {"type": "Feature", "geometry": mapping(g), "properties": {"name": f"Scarp edge {i + 1} (synthetic)"}} for i, g in enumerate(rims)])))

    trav = json.loads(TRAVERSE.read_text())["points"]                # [sol, east m, north m] from the landing site
    pts = np.array(trav, float)
    depot = pts[(pts[:, 0] >= 653) & (pts[:, 0] <= 690)]
    dlon, dlat = _local_to_lonlat(depot[:, 1].mean(), depot[:, 2].mean())
    (out / "vectors" / "science_targets.geojson").write_text(json.dumps(fc([
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(dlon), float(dlat)]},
         "properties": {"name": "Three Forks sample depot", "code": "THREE_FORKS", "scienceValue": 0.5}}])))
    step = max(1, len(pts) // 1500)
    plon, plat = _local_to_lonlat(pts[::step, 1], pts[::step, 2])
    (out / "vectors" / "rover_path.geojson").write_text(json.dumps(fc([
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[float(a), float(b)] for a, b in zip(plon, plat)]},
         "properties": {"name": "Perseverance traverse, sols 14-2022 (MMGIS, via the 3D repo)"}}])))

    inner = 2 * CELL
    ra_w, ra_n = eqc_to_lonlat(x0 + inner, y1 - inner)
    ra_e, ra_s = eqc_to_lonlat(x0 + W * CELL - inner, y1 - H * CELL + inner)
    ra = {"type": "Polygon", "coordinates": [[[float(ra_w), float(ra_s)], [float(ra_e), float(ra_s)], [float(ra_e), float(ra_n)],
                                              [float(ra_w), float(ra_n)], [float(ra_w), float(ra_s)]]]}
    (out / "vectors" / "routable_area.geojson").write_text(json.dumps(fc([{"type": "Feature", "geometry": ra, "properties": {}}])))
    (out / "demo_window.json").write_text(json.dumps({
        "startSol": 0, "endSol": 29, "startUtc": "2021-02-18T00:00:00Z", "endUtc": "2021-03-20T00:00:00Z",
        "solarLongitudeStart": None, "solarLongitudeEnd": None,
        "source": "DEMONSTRATION placeholder: replace with the latest 30 sols of the public MEDA release",
        "dataState": "DEMONSTRATION_DATA"}, indent=2))
    obs = out / "meda" / "observations.csv"
    if obs.exists():
        obs.unlink()
