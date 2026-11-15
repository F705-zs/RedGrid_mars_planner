#!/usr/bin/env python3
"""Clean and prepare raw Jezero Crater & MEDA datasets into the RedGrid Prepared-Data Contract."""
from __future__ import annotations

import csv
import json
import math
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pyogrio.raw
import rasterio
import rasterio.features
import rasterio.warp
import shapely
from rasterio.enums import Resampling
from rasterio.transform import Affine
from scipy.ndimage import label
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

R_MARS_M = 3_396_190.0
PROJ4_EQC = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
PROJ4_LONLAT = "+proj=longlat +R=3396190 +no_defs"
REGION_BOX = box(77.20, 18.20, 77.70, 18.70)
INNER_CLIP_BOX = box(77.20001, 18.20001, 77.69999, 18.69999)

# 8 m grid aligned to exact multiples of 8 m inside the Jezero Crater region box
GRID_X0 = 4_576_008.0
GRID_Y_TOP = 1_108_432.0
GRID_W = 3704
GRID_H = 3704
CELL_M = 8.0
GRID_TRANSFORM = Affine(CELL_M, 0.0, GRID_X0, 0.0, -CELL_M, GRID_Y_TOP)

# Base terrain class mapping from USGS SIM 3464 GeoUnits_v1 symbol -> class code
# Matches terrain_class_mapping table in redgrid_schema.sql:
# 1 = REGOLITH, 2 = BEDROCK, 3 = SAND, 4 = BOULDER_FIELD
SYMBOL_TO_TERRAIN_CLASS = {
    "Aeb": 3,    # Eolian bedform unit -> SAND
    "su": 1,     # Smooth unit, undivided -> REGOLITH
    "ci": 1,     # Crater interior unit -> REGOLITH
    "Njf": 2,    # Jezero floor unit -> BEDROCK
    "NHjf1": 2,  # Jezero fan 1 unit -> BEDROCK
    "NHjf2": 2,  # Jezero fan 2 unit -> BEDROCK
    "Hnpf": 2,   # Nili Planum fan unit -> BEDROCK
    "Nue": 2,    # Upper etched unit -> BEDROCK
    "Nle": 2,    # Lower etched unit -> BEDROCK
    "Nnp1": 2,   # Nili Planum 1 unit -> BEDROCK
    "Nnp2": 2,   # Nili Planum 2 unit -> BEDROCK
    "Nrb": 2,    # Rugged bright unit -> BEDROCK
    "cr": 4,     # Crater rim unit -> BOULDER_FIELD
    "CR": 4,     # Crater riim unit -> BOULDER_FIELD
    "ce": 4,     # Crater ejecta unit -> BOULDER_FIELD
}

# Constants from planning_constant table in redgrid_schema.sql
TI_SAND_MAX = 200.0
TI_BEDROCK_MIN = 600.0
HAZARD_ROUGHNESS_M = 1.0
HAZARD_MIN_AREA_M2 = 192.0
SCARP_SLOPE_DEG = 25.0
SCARP_MIN_LENGTH_M = 50.0
COMM_TX_LON = 77.45042334
COMM_TX_LAT = 18.44479586
COMM_TX_HEIGHT_M = 18.0
COMM_RX_HEIGHT_M = 2.0


def lonlat_to_eqc(lon: float, lat: float) -> tuple[float, float]:
    return math.radians(lon) * R_MARS_M, math.radians(lat) * R_MARS_M


def eqc_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / R_MARS_M), math.degrees(y / R_MARS_M)


def write_tif(path: Path, arr: np.ndarray, dtype: str, nodata: float | int, transform: Affine = GRID_TRANSFORM) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    profile = {
        "driver": "GTiff",
        "height": h,
        "width": w,
        "count": 1,
        "dtype": dtype,
        "crs": PROJ4_EQC,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)


def compute_elevation_and_roughness(hirise_dtm_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Compute 8 m mean elevation and best-fit-plane residual std roughness from 1 m HiRISE DTM."""
    print("[1/8] Computing 8 m elevation.tif and roughness.tif from 1 m HiRISE DTM...")
    t0 = time.time()
    elev = np.full((GRID_H, GRID_W), -9999.0, dtype=np.float32)
    rough = np.full((GRID_H, GRID_W), -9999.0, dtype=np.float32)

    u = np.arange(8, dtype=np.float64) - 3.5
    U, V = np.meshgrid(u, u)
    U = U.reshape(1, 1, 8, 8)
    V = V.reshape(1, 1, 8, 8)

    with rasterio.open(hirise_dtm_path) as ds:
        # Offset in 1m pixels from ds origin (4576006.6488, 1108436.8437) to (4576008.0, 1108432.0)
        col_off = int(round(GRID_X0 - ds.bounds.left))        # 1
        row_off = int(round(ds.bounds.top - GRID_Y_TOP))      # 5
        strip_h = 232
        for r0 in range(0, GRID_H, strip_h):
            r1 = min(GRID_H, r0 + strip_h)
            bh = r1 - r0
            win = rasterio.windows.Window(col_off, row_off + r0 * 8, GRID_W * 8, bh * 8)
            raw = ds.read(1, window=win)
            blocks = raw.reshape(bh, 8, GRID_W, 8).transpose(0, 2, 1, 3)
            valid = np.isfinite(blocks) & (blocks > -1e30) & (blocks != ds.nodata)
            all_valid = valid.all(axis=(-2, -1))

            b_valid = np.where(all_valid[..., None, None], blocks, 0.0).astype(np.float64)
            mean_z = b_valid.mean(axis=(-2, -1))
            dz = b_valid - mean_z[..., None, None]
            var_z = (dz * dz).mean(axis=(-2, -1))
            a = (dz * U).sum(axis=(-2, -1)) / 336.0
            b = (dz * V).sum(axis=(-2, -1)) / 336.0
            res_var = np.maximum(0.0, var_z - 5.25 * (a * a + b * b))

            elev[r0:r1] = np.where(all_valid, mean_z.astype(np.float32), -9999.0)
            rough[r0:r1] = np.where(all_valid, np.sqrt(res_var).astype(np.float32), -9999.0)

    print(f"      Done in {time.time() - t0:.1f}s. Valid 8 m cells: {(elev != -9999.0).sum():,}")
    return elev, rough


def compute_slope_and_hillshade(elev: np.ndarray, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute Horn 3x3 slope (deg) and hillshade (0..254, 255 nodata) with anisotropic ground spacing."""
    print("[2/8] Computing 8 m slope.tif and hillshade.tif (Horn's method)...")
    p = np.pad(elev, 1, mode="edge")
    center = p[1:-1, 1:-1]
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            sl = p[1 + dr : 1 + dr + GRID_H, 1 + dc : 1 + dc + GRID_W]
            bad = sl == -9999.0
            sl[bad] = center[bad]

    dx = CELL_M * math.cos(math.radians(18.45))
    dy = CELL_M
    dzdx = ((p[:-2, 2:] + 2.0 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2.0 * p[1:-1, :-2] + p[2:, :-2])) / (8.0 * dx)
    dzdy = ((p[2:, :-2] + 2.0 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2.0 * p[:-2, 1:-1] + p[:-2, 2:])) / (8.0 * dy)

    slope_rad = np.arctan(np.hypot(dzdx, dzdy))
    slope_deg = np.degrees(slope_rad).astype(np.float32)
    slope_deg = np.clip(slope_deg, 0.0, 90.0)
    slope_out = np.where(valid_mask, slope_deg, -9999.0).astype(np.float32)

    # Hillshade: azimuth 315 deg, altitude 45 deg
    az = math.radians(315.0)
    alt = math.radians(45.0)
    aspect = np.arctan2(dzdy, -dzdx)
    shade = np.sin(alt) * np.cos(slope_rad) + np.cos(alt) * np.sin(slope_rad) * np.cos(az - aspect)
    hs = np.clip(shade * 254.0, 0.0, 254.0).astype(np.uint8)
    hs_out = np.where(valid_mask, hs, 255).astype(np.uint8)
    return slope_out, hs_out


def compute_viewshed(elev: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """Fast vectorized radial viewshed from the seeded Comms tower including Mars curvature drop."""
    print("[3/8] Computing 8 m comm_coverage.tif (radial viewshed with Mars curvature)...")
    t0 = time.time()
    tx_x, tx_y = lonlat_to_eqc(COMM_TX_LON, COMM_TX_LAT)
    tc = int((tx_x - GRID_X0) // CELL_M)
    tr = int((GRID_Y_TOP - tx_y) // CELL_M)
    z0 = float(elev[tr, tc]) + COMM_TX_HEIGHT_M

    out = np.full((GRID_H, GRID_W), 255, dtype=np.uint8)
    out[valid_mask] = 0
    out[tr, tc] = 1

    # Generate dense perimeter targets at 0.35-pixel angular step so every grid cell is sampled
    max_r = max(tr, GRID_H - 1 - tr)
    max_c = max(tc, GRID_W - 1 - tc)
    max_dist_px = int(math.ceil(math.hypot(max_r, max_c)))
    n_angles = int(math.ceil(2.0 * math.pi * max_dist_px * 2.0))
    angles = np.linspace(0.0, 2.0 * math.pi, n_angles, endpoint=False)

    dx_scale = CELL_M * math.cos(math.radians(18.45))
    dy_scale = CELL_M

    steps = np.arange(1, max_dist_px + 1, dtype=np.float32)  # shape (S,)
    batch_size = 1024
    for i0 in range(0, n_angles, batch_size):
        ang = angles[i0 : i0 + batch_size]
        sin_a = np.sin(ang)[:, None]  # (B, 1)
        cos_a = np.cos(ang)[:, None]  # (B, 1)

        rr = np.rint(tr + sin_a * steps[None, :]).astype(np.int32)
        cc = np.rint(tc + cos_a * steps[None, :]).astype(np.int32)
        in_bounds = (rr >= 0) & (rr < GRID_H) & (cc >= 0) & (cc < GRID_W)

        rr_clip = np.clip(rr, 0, GRID_H - 1)
        cc_clip = np.clip(cc, 0, GRID_W - 1)

        z = elev[rr_clip, cc_clip]
        v = in_bounds & (z != -9999.0)

        dist_m = np.hypot((cc_clip - tc) * dx_scale, (rr_clip - tr) * dy_scale)
        dist_m = np.maximum(dist_m, 1.0)
        drop_m = (dist_m * dist_m) / (2.0 * R_MARS_M)

        # Terrain obstruction angle and receiver angle from transmitter z0
        alpha_obs = np.where(v, (z - drop_m - z0) / dist_m, -1e9)
        alpha_rx = (z + COMM_RX_HEIGHT_M - drop_m - z0) / dist_m

        # Running max obstruction angle strictly prior to step s
        max_prior = np.maximum.accumulate(alpha_obs, axis=1)
        max_prior_prev = np.empty_like(max_prior)
        max_prior_prev[:, 0] = -1e9
        max_prior_prev[:, 1:] = max_prior[:, :-1]

        vis = v & (alpha_rx >= max_prior_prev - 1e-6)
        vis_r = rr_clip[vis]
        vis_c = cc_clip[vis]
        out[vis_r, vis_c] = 1

    covered_pct = (out[valid_mask] == 1).mean() * 100.0
    print(f"      Done in {time.time() - t0:.1f}s. Covered fraction: {covered_pct:.1f}%")
    return out


def compute_geology_and_terrain_class(
    gdb_path: Path, themis_ti_path: Path, valid_mask: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[dict], list[dict]]:
    """Reproject SIM 3464 geology & landing ellipse, resample THEMIS TI, and build terrain_class.tif."""
    print("[4/8] Processing USGS SIM 3464 geology, landing ellipse, and THEMIS thermal inertia...")

    # 1. Resample THEMIS thermal inertia onto 8 m grid
    ti_grid = np.full((GRID_H, GRID_W), -9999.0, dtype=np.float32)
    with rasterio.open(themis_ti_path) as src:
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=ti_grid,
            src_transform=src.transform,
            src_crs=PROJ4_EQC,
            dst_transform=GRID_TRANSFORM,
            dst_crs=PROJ4_EQC,
            resampling=Resampling.nearest,
            dst_nodata=-9999.0,
        )
    ti_grid[ti_grid <= 0.0] = -9999.0

    # 2. LandingEllipse -> Mars 2000 lon/lat
    meta_le, _, geoms_le, _ = pyogrio.raw.read(str(gdb_path), layer="LandingEllipse")
    src_crs = meta_le["crs"]
    g_le = shapely.from_wkb(geoms_le[0])
    g_le_ll = shape(rasterio.warp.transform_geom(src_crs, PROJ4_LONLAT, mapping(g_le)))
    if not g_le_ll.is_valid:
        g_le_ll = shapely.make_valid(g_le_ll)
    landing_ellipse_features = [
        {
            "type": "Feature",
            "properties": {
                "name": "Jezero Landing Ellipse",
                "code": "JEZERO_ELLIPSE",
            },
            "geometry": mapping(g_le_ll),
        }
    ]

    # 3. GeoUnits_v1 -> clip to REGION_BOX for geology_units.geojson and rasterize in EQC for terrain_class.tif
    meta_gu, _, geoms_gu, fields_gu = pyogrio.raw.read(str(gdb_path), layer="GeoUnits_v1")
    field_names = meta_gu["fields"].tolist()
    names = fields_gu[field_names.index("name")]
    symbols = fields_gu[field_names.index("symbol")]
    units = fields_gu[field_names.index("unit")]

    geology_features = []
    eqc_shapes_for_raster = []

    for i in range(len(geoms_gu)):
        g = shapely.from_wkb(geoms_gu[i])
        if g is None or g.is_empty:
            continue
        sym = str(symbols[i]).strip()
        uname = str(names[i]).strip()
        ucode = str(units[i]).strip()
        t_class = SYMBOL_TO_TERRAIN_CLASS.get(sym, 1)

        g_ll = shape(rasterio.warp.transform_geom(src_crs, PROJ4_LONLAT, mapping(g)))
        if not g_ll.is_valid:
            g_ll = shapely.make_valid(g_ll)
        if not g_ll.intersects(INNER_CLIP_BOX):
            continue
        clipped_ll = g_ll.intersection(INNER_CLIP_BOX)
        if clipped_ll.is_empty:
            continue
        if clipped_ll.geom_type == "GeometryCollection":
            polys = [p for p in clipped_ll.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
            if not polys:
                continue
            clipped_ll = unary_union(polys)
        if clipped_ll.geom_type not in ("Polygon", "MultiPolygon"):
            continue

        geology_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": uname,
                    "code": sym,
                    "unit": ucode,
                    "baseTerrainClass": t_class,
                },
                "geometry": mapping(clipped_ll),
            }
        )

        # Transform clipped polygon to EQC for rasterization
        g_eqc = shape(rasterio.warp.transform_geom(PROJ4_LONLAT, PROJ4_EQC, mapping(clipped_ll)))
        if not g_eqc.is_valid:
            g_eqc = shapely.make_valid(g_eqc)
        if not g_eqc.is_empty:
            eqc_shapes_for_raster.append((g_eqc, t_class))

    # Rasterize onto 8 m grid (default 1 = REGOLITH inside valid mask)
    tclass = rasterio.features.rasterize(
        eqc_shapes_for_raster,
        out_shape=(GRID_H, GRID_W),
        transform=GRID_TRANSFORM,
        fill=1,
        dtype=np.uint8,
    )

    # Refine REGOLITH (1) using THEMIS thermal inertia where TI is valid (> 0)
    reg_mask = (tclass == 1) & (ti_grid > 0.0)
    tclass = np.where(reg_mask & (ti_grid < TI_SAND_MAX), 3, tclass)
    tclass = np.where(reg_mask & (ti_grid > TI_BEDROCK_MIN), 2, tclass)

    # Apply valid footprint mask (255 = nodata outside valid footprint)
    tclass_out = np.where(valid_mask, tclass, 255).astype(np.uint8)
    print(f"      Geology features in Jezero box: {len(geology_features)}")
    return tclass_out, ti_grid, geology_features, landing_ellipse_features


def derive_vectors(
    elev: np.ndarray,
    slope: np.ndarray,
    rough: np.ndarray,
    tclass: np.ndarray,
    valid_mask: np.ndarray,
    raw_dir: Path,
) -> dict[str, dict]:
    """Derive routable_area, hazards, rim_scarps, rover_path, science_targets, safe_points, comm_assets."""
    print("[5/8] Deriving vector GeoJSON datasets...")

    # 1. routable_area.geojson
    routable_mask = (
        valid_mask
        & (elev != -9999.0)
        & (slope != -9999.0)
        & (rough != -9999.0)
        & (tclass != 255)
    )
    poly_eqc_list = []
    for geom_dict, val in rasterio.features.shapes(
        routable_mask.astype(np.uint8), mask=routable_mask, connectivity=4, transform=GRID_TRANSFORM
    ):
        if val == 1:
            poly_eqc_list.append(shape(geom_dict))
    routable_eqc = unary_union(poly_eqc_list).simplify(4.0, preserve_topology=True)
    routable_ll = shape(rasterio.warp.transform_geom(PROJ4_EQC, PROJ4_LONLAT, mapping(routable_eqc)))
    if not routable_ll.is_valid:
        routable_ll = shapely.make_valid(routable_ll)
    routable_ll = routable_ll.intersection(INNER_CLIP_BOX)
    if not routable_ll.is_valid:
        routable_ll = shapely.make_valid(routable_ll)

    routable_area_gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Jezero HiRISE Routable Footprint"},
                "geometry": mapping(routable_ll),
            }
        ],
    }

    # 2. hazards.geojson: connected squares (8-connectivity) with roughness >= 1.0 m and area >= 192.0 m^2
    s8 = np.ones((3, 3), dtype=int)
    lbl_h, n_h = label(valid_mask & (rough >= HAZARD_ROUGHNESS_M), structure=s8)
    h_sizes = np.bincount(lbl_h.ravel())
    keep_labels = np.where((np.arange(len(h_sizes)) > 0) & (h_sizes * (CELL_M * CELL_M) >= HAZARD_MIN_AREA_M2))[0]

    hazard_features = []
    for idx, comp_id in enumerate(keep_labels, start=1):
        rr, cc = np.where(lbl_h == comp_id)
        boxes = []
        for r, c in zip(rr, cc):
            x0 = GRID_X0 + c * CELL_M
            y1 = GRID_Y_TOP - r * CELL_M
            # Slight 0.05m buffer ensures diagonal-touching cells merge into a single valid Polygon
            boxes.append(box(x0 - 0.05, y1 - CELL_M - 0.05, x0 + CELL_M + 0.05, y1 + 0.05))
        comp_eqc = unary_union(boxes)
        comp_ll = shape(rasterio.warp.transform_geom(PROJ4_EQC, PROJ4_LONLAT, mapping(comp_eqc)))
        if not comp_ll.is_valid:
            comp_ll = shapely.make_valid(comp_ll)
        comp_ll = comp_ll.intersection(INNER_CLIP_BOX)
        area_m2 = float(len(rr) * CELL_M * CELL_M)
        max_r = float(rough[rr, cc].max())
        hazard_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": f"Roughness Hazard {idx}",
                    "code": f"HAZ_{idx:03d}",
                    "areaM2": round(area_m2, 1),
                    "maxRoughnessM": round(max_r, 3),
                },
                "geometry": mapping(comp_ll),
            }
        )

    # 3. rim_scarps.geojson: edges of areas with slope >= 25.0 deg and length >= 50.0 m
    steep_mask = valid_mask & (slope >= SCARP_SLOPE_DEG)
    scarp_features = []
    scarp_idx = 0
    for geom_dict, val in rasterio.features.shapes(
        steep_mask.astype(np.uint8), mask=steep_mask, connectivity=8, transform=GRID_TRANSFORM
    ):
        if val != 1:
            continue
        poly_eqc = shape(geom_dict)
        line_eqc = poly_eqc.exterior.simplify(4.0, preserve_topology=False)
        if line_eqc.length < SCARP_MIN_LENGTH_M or len(line_eqc.coords) < 2:
            continue
        line_ll = shape(rasterio.warp.transform_geom(PROJ4_EQC, PROJ4_LONLAT, mapping(line_eqc)))
        if not line_ll.is_valid or line_ll.is_empty:
            continue
        scarp_idx += 1
        scarp_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": f"Rim Scarp {scarp_idx}",
                    "code": f"SCARP_{scarp_idx:04d}",
                    "lengthM": round(float(line_eqc.length), 1),
                },
                "geometry": mapping(line_ll),
            }
        )

    # 4. rover_path.geojson: M20_traverse.json cut at demo_window.end_sol (sol <= 1859)
    with open(raw_dir / "M20_traverse.json", "r", encoding="utf-8") as f:
        m20_raw = json.load(f)

    rover_features = []
    sol_to_coord: dict[int, tuple[float, float]] = {}
    for ft in m20_raw["features"]:
        props = ft.get("properties") or {}
        sol = int(props.get("sol", 0))
        if sol > 1859:
            continue
        coords_raw = ft["geometry"]["coordinates"]
        coords_2d = [[float(c[0]), float(c[1])] for c in coords_raw]
        if len(coords_2d) < 2:
            continue
        line = LineString(coords_2d)
        if not line.is_valid or line.is_empty:
            continue
        sol_to_coord[sol] = (coords_2d[-1][0], coords_2d[-1][1])
        from_rmc = props.get("fromRMC", "")
        to_rmc = props.get("toRMC", "")
        rover_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": f"Perseverance Drive Sol {sol} ({from_rmc} to {to_rmc})",
                    "code": f"SOL_{sol:04d}_{to_rmc}",
                    "sol": sol,
                    "lengthM": round(float(props.get("length", 0.0)), 2),
                },
                "geometry": mapping(line),
            }
        )

    # 5. science_targets.geojson: Perseverance sample sites (1.0 for rock-core, 0.5 for regolith/atmo/depot)
    raw_sites = [
        {"code": "ROUBION", "name": "Roubion (Atmosphere Sample)", "sol": 164, "sampleType": "ATMOSPHERE", "scienceValue": 0.5},
        {"code": "MONTDENIER", "name": "Montdenier & Montagnac (Rochette Core)", "sol": 190, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "SALETTE", "name": "Salette & Coulettes (Brac Core)", "sol": 257, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "ROBINE", "name": "Robine & Malay (Issole Core)", "sol": 295, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "HAHONI", "name": "Ha'ahoni & Atsah (Sid Core)", "sol": 371, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "SKINNER_RIDGE", "name": "Swift Run & Skyland (Skinner Ridge Core)", "sol": 490, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "WILDCAT_RIDGE", "name": "Hazeltop & Bearwallow (Wildcat Ridge Core)", "sol": 509, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "AMALIK", "name": "Shuyak & Mageik (Amalik Core)", "sol": 575, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "HIDDEN_HARBOR", "name": "Kukaklek (Hidden Harbor Core)", "sol": 623, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "OBSERVATION_MTN", "name": "Atmo Mountain & Crosswind Lake (Regolith)", "sol": 634, "sampleType": "REGOLITH", "scienceValue": 0.5},
        {"code": "THREE_FORKS_DEPOT", "name": "Three Forks Sample Depot", "sol": 652, "sampleType": "SAMPLE_DEPOT", "scienceValue": 0.5, "lon": 77.4342, "lat": 18.4450},
        {"code": "BEREA", "name": "Melyn (Berea Carbonate Core)", "sol": 749, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "OTIS_PEAK", "name": "Otis Peak (Emerald Lake Core)", "sol": 832, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "DREAM_LAKE", "name": "Pilot Mountain (Dream Lake Core)", "sol": 913, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "PELICAN_POINT", "name": "Pelican Point (Margin Unit Core)", "sol": 949, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "LEFROY_BAY", "name": "Lefroy Bay (Hydrated Silica Core)", "sol": 979, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "COMET_GEYSER", "name": "Comet Geyser (Bunsen Peak Core)", "sol": 1088, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
        {"code": "CHEYAVA_FALLS", "name": "Sapphire Canyon (Cheyava Falls Core)", "sol": 1215, "sampleType": "ROCK_CORE", "scienceValue": 1.0},
    ]

    traversable = routable_mask & (slope < 28.0) & (rough < 0.9) & (lbl_h == 0)
    science_features = []
    for site in raw_sites:
        if "lon" in site and "lat" in site:
            lon, lat = float(site["lon"]), float(site["lat"])
        else:
            bsol = max([s for s in sol_to_coord if s <= site["sol"]], default=min(sol_to_coord))
            lon, lat = sol_to_coord[bsol]
        # Verify cell is traversable; if on a steep/rough pixel, snap to nearest traversable cell
        x, y = lonlat_to_eqc(lon, lat)
        c = int((x - GRID_X0) // CELL_M)
        r = int((GRID_Y_TOP - y) // CELL_M)
        if not (0 <= r < GRID_H and 0 <= c < GRID_W and traversable[r, c]):
            for rad in range(1, 20):
                r0, r1 = max(0, r - rad), min(GRID_H, r + rad + 1)
                c0, c1 = max(0, c - rad), min(GRID_W, c + rad + 1)
                sub = traversable[r0:r1, c0:c1]
                if sub.any():
                    dr, dc = np.argwhere(sub)[0]
                    r, c = r0 + int(dr), c0 + int(dc)
                    lon, lat = eqc_to_lonlat(GRID_X0 + (c + 0.5) * CELL_M, GRID_Y_TOP - (r + 0.5) * CELL_M)
                    break

        science_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": site["name"],
                    "code": site["code"],
                    "sol": site["sol"],
                    "sampleType": site["sampleType"],
                    "scienceValue": float(site["scienceValue"]),
                },
                "geometry": mapping(Point(round(lon, 7), round(lat, 7))),
            }
        )

    # 6. safe_points.geojson & comm_assets.geojson (matching schema seed codes BASE and COMM1 + Three Forks Depot)
    safe_points_gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Ares Base One (concept habitat)",
                    "code": "BASE",
                    "providesRefill": True,
                },
                "geometry": {"type": "Point", "coordinates": [77.45088573, 18.44462715]},
            },
            {
                "type": "Feature",
                "properties": {
                    "name": "Three Forks Sample Depot",
                    "code": "THREE_FORKS_DEPOT",
                    "providesRefill": False,
                },
                "geometry": {"type": "Point", "coordinates": [77.4342, 18.4450]},
            },
        ],
    }

    comm_assets_gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Comms tower",
                    "code": "COMM1",
                    "heightM": 18.0,
                },
                "geometry": {"type": "Point", "coordinates": [COMM_TX_LON, COMM_TX_LAT]},
            }
        ],
    }

    print(
        f"      Derived vectors: hazards={len(hazard_features)}, rim_scarps={len(scarp_features)}, "
        f"rover_path={len(rover_features)}, science_targets={len(science_features)}"
    )
    return {
        "routable_area.geojson": routable_area_gj,
        "hazards.geojson": {"type": "FeatureCollection", "features": hazard_features},
        "rim_scarps.geojson": {"type": "FeatureCollection", "features": scarp_features},
        "rover_path.geojson": {"type": "FeatureCollection", "features": rover_features},
        "science_targets.geojson": {"type": "FeatureCollection", "features": science_features},
        "safe_points.geojson": safe_points_gj,
        "comm_assets.geojson": comm_assets_gj,
    }


def prepare_display_rasters(raw_dir: Path, out_dir: Path) -> None:
    """Prepare imagery_hirise.tif, imagery_ctx.tif, and elevation_ctx.tif in PROJ4_EQC."""
    print("[6/8] Preparing display rasters (imagery_hirise.tif, imagery_ctx.tif, elevation_ctx.tif)...")
    # 1. imagery_hirise.tif (link or copy hirise_ortho_jezero.tif which is already clipped in PROJ4_EQC)
    src_hirise = raw_dir / "hirise_ortho_jezero.tif"
    dst_hirise = out_dir / "imagery_hirise.tif"
    if dst_hirise.exists():
        dst_hirise.unlink()
    try:
        os.link(src_hirise, dst_hirise)
    except OSError:
        shutil.copy2(src_hirise, dst_hirise)

    # Region bounds in PROJ4_EQC
    min_x, min_y = lonlat_to_eqc(77.20, 18.20)
    max_x, max_y = lonlat_to_eqc(77.70, 18.70)

    # 2. imagery_ctx.tif from JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif
    src_ctx_img = raw_dir / "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif"
    with rasterio.open(src_ctx_img) as ds:
        win = rasterio.windows.from_bounds(min_x, min_y, max_x, max_y, transform=ds.transform)
        win = win.round_offsets().round_lengths()
        arr = ds.read(1, window=win)
        transform = ds.window_transform(win)
        write_tif(out_dir / "imagery_ctx.tif", arr, "uint8", 0, transform=transform)

    # 3. elevation_ctx.tif from JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif
    src_ctx_dem = raw_dir / "JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif"
    with rasterio.open(src_ctx_dem) as ds:
        win = rasterio.windows.from_bounds(min_x, min_y, max_x, max_y, transform=ds.transform)
        win = win.round_offsets().round_lengths()
        arr = ds.read(1, window=win)
        valid = np.isfinite(arr) & (arr > -1e30)
        if ds.nodata is not None:
            valid &= arr != ds.nodata
        arr_clean = np.where(valid, arr.astype(np.float32), -9999.0)
        transform = ds.window_transform(win)
        write_tif(out_dir / "elevation_ctx.tif", arr_clean, "float32", -9999.0, transform=transform)


def clean_meda_and_demo_window(raw_dir: Path, out_dir: Path) -> None:
    """Clean MEDA Sol 1830..1859 CSVs into meda/observations.csv and demo_window.json."""
    print("[7/8] Cleaning MEDA Sol 1830..1859 observations and creating demo_window.json...")
    meda_raw = raw_dir / "meda"
    meda_out = out_dir / "meda"
    meda_out.mkdir(parents=True, exist_ok=True)

    # Mars 2020 SCLK epoch (2000-01-01T11:58:55.816Z)
    sclk_epoch = datetime(2000, 1, 1, 11, 58, 56, tzinfo=timezone.utc)
    sclk_min = None
    sclk_max = None

    obs_rows = []
    for sol in range(1830, 1860):
        sdir = meda_raw / f"sol_{sol}"
        if not sdir.exists():
            continue

        # 1. Ancillary SCLK range
        for fn in sorted(os.listdir(sdir)):
            fp = sdir / fn
            if "DER_ANCILLARY" in fn:
                with open(fp, "r", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        if r.get("SCLK"):
                            s = float(r["SCLK"])
                            if sclk_min is None or s < sclk_min:
                                sclk_min = s
                            if sclk_max is None or s > sclk_max:
                                sclk_max = s

            # 2. Pressure (DER_PS) -> aggregate hourly by LMST hour (00..23)
            elif "DER_PS" in fn:
                hourly_p: dict[int, list[float]] = {}
                hourly_ts: dict[int, str] = {}
                with open(fp, "r", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        val_str = r.get("PRESSURE", "").strip()
                        lmst = r.get("LMST", "").strip()
                        if not val_str or not lmst or "M" not in lmst:
                            continue
                        val = float(val_str)
                        if not (400.0 <= val <= 1200.0):
                            continue
                        hr = int(lmst.split("M")[1].split(":")[0])
                        hourly_p.setdefault(hr, []).append(val)
                        hourly_ts.setdefault(hr, lmst)
                for hr in sorted(hourly_p):
                    obs_rows.append(
                        {
                            "sol": sol,
                            "observed_at": hourly_ts[hr],
                            "variable": "pressure",
                            "unit": "Pa",
                            "value": f"{np.mean(hourly_p[hr]):.3f}",
                            "source": f"NASA PDS4 mars2020_meda/data_derived_env/{fn}",
                        }
                    )

            # 3. Temperature (DER_RHS HUMIDITY_LOCAL_TEMP in K -> degC) -> aggregate hourly by LMST hour
            elif "DER_RHS" in fn:
                hourly_t: dict[int, list[float]] = {}
                hourly_ts = {}
                with open(fp, "r", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        val_str = r.get("HUMIDITY_LOCAL_TEMP", "").strip()
                        lmst = r.get("LMST", "").strip()
                        if not val_str or not lmst or "M" not in lmst:
                            continue
                        val_k = float(val_str)
                        if not (150.0 <= val_k <= 320.0):
                            continue
                        val_c = val_k - 273.15
                        hr = int(lmst.split("M")[1].split(":")[0])
                        hourly_t.setdefault(hr, []).append(val_c)
                        hourly_ts.setdefault(hr, lmst)
                for hr in sorted(hourly_t):
                    obs_rows.append(
                        {
                            "sol": sol,
                            "observed_at": hourly_ts[hr],
                            "variable": "temperature",
                            "unit": "degC",
                            "value": f"{np.mean(hourly_t[hr]):.3f}",
                            "source": f"NASA PDS4 mars2020_meda/data_derived_env/{fn}",
                        }
                    )

    obs_csv_path = meda_out / "observations.csv"
    with open(obs_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sol", "observed_at", "variable", "unit", "value", "source"])
        writer.writeheader()
        writer.writerows(obs_rows)

    start_utc = (sclk_epoch + timedelta(seconds=float(sclk_min or 829351575))).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = (sclk_epoch + timedelta(seconds=float(sclk_max or 832014810))).strftime("%Y-%m-%dT%H:%M:%SZ")

    demo_window = {
        "startSol": 1830,
        "endSol": 1859,
        "startUtc": start_utc,
        "endUtc": end_utc,
        "solarLongitudeStart": 263.4,
        "solarLongitudeEnd": 282.5,
        "source": "NASA PDS Atmospheres Node - Mars 2020 MEDA Bundle (urn:nasa:pds:mars2020_meda), Sols 1830-1859",
        "dataState": "HISTORICAL_OBSERVATION",
    }
    with open(out_dir / "demo_window.json", "w", encoding="utf-8") as f:
        json.dump(demo_window, f, indent=2)

    print(f"      Written {len(obs_rows):,} cleaned hourly MEDA records to {obs_csv_path.name}")


def clean_apollo_14_traverses(raw_dir: Path, data_dir: Path) -> list[dict]:
    """Clean Apollo 14 EVA traverse shapefiles (CDR & LMP paths for EVAs 1 & 2) into Moon lon/lat GeoJSON."""
    print("[8/9] Cleaning Apollo 14 EVA traverse shapefiles...")
    apollo_raw = raw_dir / "apollo_14"
    apollo_out = data_dir / "apollo_14"
    apollo_out.mkdir(parents=True, exist_ok=True)
    moon_lonlat_crs = "+proj=longlat +R=1737400 +no_defs"

    path_files = [
        ("APOLLO_14-1_CDR_PATHS.SHP", "Apollo 14 EVA 1 - Commander (Shepard)"),
        ("APOLLO_14-1_LMP_PATHS.SHP", "Apollo 14 EVA 1 - Lunar Module Pilot (Mitchell)"),
        ("APOLLO_14-2_CDR_PATHS.SHP", "Apollo 14 EVA 2 - Commander (Shepard)"),
        ("APOLLO_14-2_LMP_PATHS.SHP", "Apollo 14 EVA 2 - Lunar Module Pilot (Mitchell)"),
    ]
    features = []
    for shp_name, label_prefix in path_files:
        shp_path = apollo_raw / shp_name
        if not shp_path.exists():
            continue
        meta, _, geoms, fields = pyogrio.raw.read(str(shp_path))
        src_crs = meta["crs"]
        ids = fields[0] if len(fields) > 0 else range(len(geoms))
        for idx, (g_wkb, seg_id) in enumerate(zip(geoms, ids)):
            g = shapely.from_wkb(g_wkb)
            if g is None or g.is_empty or g.length <= 0:
                continue
            g_ll = shape(rasterio.warp.transform_geom(src_crs, moon_lonlat_crs, mapping(g)))
            if not g_ll.is_valid or g_ll.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "name": f"{label_prefix} Segment {int(seg_id)}",
                        "eva": 1 if "14-1" in shp_name else 2,
                        "astronaut": "CDR" if "CDR" in shp_name else "LMP",
                        "segmentId": int(seg_id),
                        "lengthM": round(float(g.length), 2),
                        "keptAside": 1 if (idx % 5 == 0) else 0,
                    },
                    "geometry": mapping(g_ll),
                }
            )

    gj = {"type": "FeatureCollection", "features": features}
    with open(apollo_out / "traverses.geojson", "w", encoding="utf-8") as f:
        json.dump(gj, f, separators=(",", ":"))
    print(f"      Cleaned {len(features)} Apollo 14 EVA path segments -> data/apollo_14/traverses.geojson")
    return features


def write_manifest(data_dir: Path) -> None:
    """Write data/manifest.json with dataset URLs and access dates matching the dataset table."""
    print("[9/9] Writing data/manifest.json...")
    accessed = "2026-11-15"
    urls = [
        ("hirise_dtm", "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif"),
        ("hirise_ortho", "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif"),
        ("ctx_dtm", "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif"),
        ("ctx_ortho", "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXortho_mosaic_5m.tif"),
        ("sim3464_geology", "https://pubs.usgs.gov/sim/3464/sim3464_database.zip"),
        ("themis_ti", "https://asc-astropedia.s3.us-west-2.amazonaws.com/Mars/Odyssey/THEMIS-Global-Thermal-Inertia-Mosaic/Quantitative-32-Bit/THEMIS_TI_Mosaic_Quant_00N060E_100mpp.cub"),
        ("m20_traverse", "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json"),
        ("meda_env", "https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda"),
        ("mars_trek", "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars"),
        ("m20_waypoints", "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"),
        ("apollo_14", "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/APOLLO_14/APOLLO_14.ZIP"),
    ]
    manifest = {
        k: {"url": u, "accessedOn": accessed, "status": "prepared"}
        for k, u in urls
    }
    with open(data_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def main() -> None:
    import sys
    fast = "--fast-update" in sys.argv
    root = Path(__file__).resolve().parents[1]
    raw_dir = Path(r"d:\Z\uni\year 4 2026-2027\NASA Challenge\Dataset\ready_to_use\ready_to_use")
    data_dir = root / "data"
    out_dir = data_dir / "jezero"
    vec_dir = out_dir / "vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    if fast and (out_dir / "elevation.tif").exists() and (out_dir / "roughness.tif").exists():
        print("[1-3/9] Loading existing elevation.tif, roughness.tif, slope.tif...")
        with rasterio.open(out_dir / "elevation.tif") as ds:
            elev = ds.read(1)
        with rasterio.open(out_dir / "roughness.tif") as ds:
            rough = ds.read(1)
        with rasterio.open(out_dir / "slope.tif") as ds:
            slope = ds.read(1)
        valid_mask = elev != -9999.0
    else:
        elev, rough = compute_elevation_and_roughness(raw_dir / "hirise_dtm_jezero.tif")
        valid_mask = elev != -9999.0
        slope, hillshade = compute_slope_and_hillshade(elev, valid_mask)
        comm = compute_viewshed(elev, valid_mask)
        write_tif(out_dir / "elevation.tif", elev, "float32", -9999.0)
        write_tif(out_dir / "roughness.tif", rough, "float32", -9999.0)
        write_tif(out_dir / "slope.tif", slope, "float32", -9999.0)
        write_tif(out_dir / "hillshade.tif", hillshade, "uint8", 255)
        write_tif(out_dir / "comm_coverage.tif", comm, "uint8", 255)

    gdb_path = raw_dir / "USGS_SIM3464_Geology" / "Geodatabase" / "Nili.gdb"
    tclass, ti_grid, geology_feats, ellipse_feats = compute_geology_and_terrain_class(
        gdb_path, raw_dir / "themis_ti_jezero.tif", valid_mask
    )

    write_tif(out_dir / "terrain_class.tif", tclass, "uint8", 255)
    write_tif(out_dir / "thermal_inertia.tif", ti_grid, "float32", -9999.0)

    vectors = derive_vectors(elev, slope, rough, tclass, valid_mask, raw_dir)
    vectors["geology_units.geojson"] = {"type": "FeatureCollection", "features": geology_feats}
    vectors["landing_ellipse.geojson"] = {"type": "FeatureCollection", "features": ellipse_feats}

    for fname, gj in vectors.items():
        with open(vec_dir / fname, "w", encoding="utf-8") as f:
            json.dump(gj, f, separators=(",", ":"))

    if not fast:
        prepare_display_rasters(raw_dir, out_dir)
        clean_meda_and_demo_window(raw_dir, out_dir)

    clean_apollo_14_traverses(raw_dir, data_dir)
    write_manifest(data_dir)

    print(f"\nAll datasets cleaned and prepared in {time.time() - t_start:.1f}s -> {out_dir}")


if __name__ == "__main__":
    main()
