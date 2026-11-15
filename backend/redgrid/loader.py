"""Loads prepared data that meets the prepared-data contract (Database Design RedGrid). Checks only; never derives data."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import box, shape

from .db import get_db

ROUTING = {"elevation.tif": "float", "slope.tif": "float", "roughness.tif": "float", "terrain_class.tif": "uint8",
           "comm_coverage.tif": "uint8", "hillshade.tif": "uint8"}
OPTIONAL_RASTERS = ("thermal_inertia.tif", "imagery_hirise.tif", "imagery_ctx.tif", "elevation_ctx.tif")
VECTORS = {"hazards": "HAZARD", "rim_scarps": "RIM_SCARP", "science_targets": "SCIENCE_TARGET", "safe_points": "SAFE_POINT",
           "comm_assets": "COMMUNICATION_ASSET", "rover_path": "ROVER_PATH", "geology_units": "TERRAIN_UNIT",
           "landing_ellipse": "LANDING_ELLIPSE"}
SEEDED_CODES = ("BASE", "COMM1")       # demonstration points seeded by the schema, kept when vectors are reloaded
REGION_BOX = box(77.20, 18.20, 77.70, 18.70)


def check_prepared(data_dir: str) -> list[str]:
    d = Path(data_dir) / "jezero"
    problems: list[str] = []
    ref = None
    for name in ROUTING:
        p = d / name
        if not p.exists():
            problems.append(f"missing {name}")
            continue
        with rasterio.open(p) as ds:
            grid = (round(ds.transform.a, 6), round(ds.transform.e, 6), round(ds.transform.c, 3), round(ds.transform.f, 3), ds.width, ds.height)
            ref = ref or (name, grid)
            if grid != ref[1]:
                problems.append(f"{name} is not on the same grid as {ref[0]}")
            if abs(ds.transform.a - 8.0) > 1e-6:
                problems.append(f"{name}: cell size must be 8 m (found {ds.transform.a})")
            if ds.crs is None or "eqc" not in ds.crs.to_proj4():
                problems.append(f"{name}: coordinate system must be Mars 2000 equirectangular")
            a = ds.read(1)
            valid = a[a != ds.nodata] if ds.nodata is not None else a.ravel()
            if name == "slope.tif" and valid.size and (valid.min() < 0 or valid.max() > 90):
                problems.append("slope.tif values must be 0-90")
            if name == "roughness.tif" and valid.size and valid.min() < 0:
                problems.append("roughness.tif values must be >= 0")
            if name == "terrain_class.tif" and not set(np.unique(a)).issubset({1, 2, 3, 4, 255}):
                problems.append("terrain_class.tif values must be 1, 2, 3, 4 or 255")
            if name == "comm_coverage.tif" and not set(np.unique(a)).issubset({0, 1, 255}):
                problems.append("comm_coverage.tif values must be 0, 1 or 255")
    ra = d / "vectors" / "routable_area.geojson"
    if not ra.exists():
        problems.append("missing vectors/routable_area.geojson")
    else:
        g = _single_geometry(json.loads(ra.read_text()))
        if g is None or not REGION_BOX.buffer(1e-9).contains(shape(g)):
            problems.append("routable_area.geojson must be one Polygon/MultiPolygon inside the region box")
    w = d / "demo_window.json"
    if not w.exists():
        problems.append("missing demo_window.json")
    else:
        win = json.loads(w.read_text())
        if win["endSol"] - win["startSol"] >= 30 or win["endSol"] < win["startSol"]:
            problems.append("demo_window.json must cover at most 30 sols")
        obs = d / "meda" / "observations.csv"
        if obs.exists():
            with obs.open() as fh:
                for row in csv.DictReader(fh):
                    if not win["startSol"] <= int(row["sol"]) <= win["endSol"]:
                        problems.append(f"observation sol {row['sol']} is outside the demo window")
                        break
    st = d / "vectors" / "science_targets.geojson"
    if st.exists():
        for f in json.loads(st.read_text()).get("features", []):
            v = f.get("properties", {}).get("scienceValue")
            if v is None or not 0 <= v <= 1:
                problems.append("every science target needs scienceValue between 0 and 1")
                break
    return problems


def _single_geometry(gj: dict):
    if gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        return feats[0]["geometry"] if len(feats) == 1 else None
    if gj.get("type") == "Feature":
        return gj["geometry"]
    return gj if gj.get("type") in ("Polygon", "MultiPolygon") else None


def load_prepared(data_dir: str, demonstration: bool = False) -> list[str]:
    problems = check_prepared(data_dir)
    if problems:
        raise SystemExit("Prepared data does not meet the contract:\n  - " + "\n  - ".join(problems))
    from .repositories.catalog import DatasetRepository, LayerRepository, RegionRepository
    from .repositories.environment import EnvironmentRepository
    con = get_db()
    d = Path(data_dir) / "jezero"
    out = []
    layers = LayerRepository(con)
    for key, ftype in VECTORS.items():
        p = d / "vectors" / f"{key}.geojson"
        if not p.exists():
            continue
        layer = layers.get_by_key(1, key)
        feats = []
        for f in json.loads(p.read_text()).get("features", []):
            pr = f.get("properties", {}) or {}
            feats.append({"featureType": ftype, "geometry": f["geometry"], "name": pr.get("name"), "code": pr.get("code"),
                          "scienceValue": pr.get("scienceValue") if ftype == "SCIENCE_TARGET" else None,
                          "providesRefill": bool(pr.get("providesRefill")) if ftype == "SAFE_POINT" else False,
                          "heightM": pr.get("heightM") if ftype == "COMMUNICATION_ASSET" else None})
        if key in ("safe_points", "comm_assets"):
            con.execute(f"DELETE FROM feature WHERE layer_id = ? AND (code IS NULL OR code NOT IN ({','.join('?' * len(SEEDED_CODES))}))",
                        (layer.id, *SEEDED_CODES))
            feats = [f for f in feats if f.get("code") not in SEEDED_CODES]
            for f in feats:
                con.execute("""INSERT INTO feature (layer_id, feature_type, name, code, geometry_json, science_value, provides_refill, height_m)
                               VALUES (?,?,?,?,?,?,?,?)""", (layer.id, f["featureType"], f["name"], f["code"], json.dumps(f["geometry"]),
                                                            None, int(f["providesRefill"]), f["heightM"]))
            n = len(feats)
        else:
            n = layers.replace_features(layer.id, feats)
        out.append(f"{key}: {n} features")
    g = _single_geometry(json.loads((d / "vectors" / "routable_area.geojson").read_text()))
    RegionRepository(con).set_routable_geometry(1, g)
    out.append(f"routable area: {shape(g).area:.5f} square degrees")
    env = EnvironmentRepository(con)
    win = json.loads((d / "demo_window.json").read_text())
    env.set_demo_window(win)
    obs_rows = []
    obs = d / "meda" / "observations.csv"
    if obs.exists():
        with obs.open() as fh:
            for row in csv.DictReader(fh):
                obs_rows.append({"sol": int(row["sol"]), "observed_at": row["observed_at"], "variable": row["variable"],
                                 "unit": row.get("unit"), "value": float(row["value"]), "source": row.get("source"),
                                 "data_state": "HISTORICAL_OBSERVATION"})
    out.append(f"demo window: sols {win['startSol']}-{win['endSol']}, {env.replace_observations(1, obs_rows)} observations")
    man = Path(data_dir) / "manifest.json"
    if man.exists():
        ds = DatasetRepository(con)
        n = sum(ds.set_accessed_on(v["url"], v["accessedOn"]) for v in json.loads(man.read_text()).values())
        out.append(f"manifest: access dates set for {n} datasets")
    apollo_gj = Path(data_dir) / "apollo_14" / "traverses.geojson"
    rover_gj = d / "vectors" / "rover_path.geojson"
    if apollo_gj.exists() or rover_gj.exists():
        con.execute("DELETE FROM training_route")
        t_rows = []
        if apollo_gj.exists():
            for idx, f in enumerate(json.loads(apollo_gj.read_text()).get("features", [])):
                pr = f.get("properties", {}) or {}
                t_rows.append((12, "HUMAN", "MOON", pr.get("name") or f"Apollo 14 Segment {idx}",
                               json.dumps(f["geometry"]), int(pr.get("keptAside", 1 if idx % 5 == 0 else 0))))
        if rover_gj.exists():
            for idx, f in enumerate(json.loads(rover_gj.read_text()).get("features", [])):
                pr = f.get("properties", {}) or {}
                t_rows.append((7, "ROVER", "MARS", pr.get("name") or f"M20 Segment {idx}",
                               json.dumps(f["geometry"]), 1 if idx % 5 == 0 else 0))
        con.executemany(
            "INSERT INTO training_route (dataset_id, agent_type, body, name, geometry_json, kept_aside) VALUES (?,?,?,?,?,?)",
            t_rows,
        )
        con.execute("INSERT OR IGNORE INTO training_dataset_link (model_id, dataset_id) VALUES (1, 7), (1, 12)")
        out.append(f"training_route: {len(t_rows)} routes")
    if demonstration:
        con.execute("UPDATE layer SET data_state = 'DEMONSTRATION_DATA' WHERE key IN "
                    "('elevation','hillshade','slope','roughness','terrain_class','comm_coverage','hazards','rim_scarps')")
    con.commit()
    return out
