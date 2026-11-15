"""Behaviours that need special set-ups: corridor widening, warnings, blocked ends, no refill point, the CLI,
the loader rejecting bad files, HTTP priority/sensor providers, training-side repository methods."""
import json
import shutil
import sqlite3
import threading

import numpy as np
import pytest
import rasterio
from flask import Flask, jsonify
from werkzeug.serving import make_server

from conftest import LANDING, ll


def mission(client, body, **over):
    r = client.post("/api/missions", json={**body, **over})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


# ------------------------------------------------------------------ routing behaviours
def test_corridor_widens_around_a_long_wall(client, mission_body):
    s, d = ll(-300, 0), ll(300, 0)
    mid = mission(client, mission_body, startLon=s[0], startLat=s[1], destLon=d[0], destLat=d[1])
    for north in range(-1400, 1401, 140):                       # HIGH warnings forming a 2.8 km wall across the trip
        lon, lat = ll(0, north)
        client.post(f"/api/missions/{mid}/annotations", json={"kind": "HAZARD_WARNING", "lon": lon, "lat": lat,
                                                               "severity": "HIGH", "radiusM": 100})
    routes = client.post(f"/api/missions/{mid}/routes").get_json()
    r = routes[1]                                               # SHORTEST
    assert r["feasible"] and r["distanceM"] > 2500              # had to go round the end of the wall
    width_deg = r["window"]["north"] - r["window"]["south"]
    assert width_deg * 59200 > 2 * 1400                         # corridor was widened beyond the first 1 km margin


def test_medium_warning_counts_as_hazard(client, mission_body):
    """A MEDIUM warning around the destination cannot be avoided: it must be counted and raise the risk."""
    mid = mission(client, mission_body)
    client.post(f"/api/missions/{mid}/annotations", json={"kind": "HAZARD_WARNING", "lon": mission_body["destLon"],
                                                           "lat": mission_body["destLat"], "severity": "MEDIUM", "radiusM": 60})
    for r in client.post(f"/api/missions/{mid}/routes").get_json():
        assert r["feasible"] and r["hazardCount"] >= 1 and r["overallRisk"] == "HIGH"
        assert any("passes within" in w for w in r["warnings"])


def _steep_point(app, threshold=25):
    from redgrid.geo import eqc_to_lonlat
    with rasterio.open(f"{app.config['DATA_DIR']}/jezero/slope.tif") as ds:
        r, c = np.argwhere(ds.read(1) > threshold)[0]
        x, y = ds.xy(int(r), int(c))
    return tuple(float(v) for v in eqc_to_lonlat(x, y))


def test_destination_on_blocked_ground(app, client, mission_body):
    lon, lat = _steep_point(app)
    mid = mission(client, mission_body, destLon=lon, destLat=lat)
    for r in client.post(f"/api/missions/{mid}/routes").get_json():
        assert not r["feasible"] and "destination is on blocked ground" in r["returnFeasibility"]["reason"]
        assert r["missionMatch"] == 0 and any("No route found" in w for w in r["warnings"])


def test_no_refill_point_at_all(app, client, mission_body):
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute("UPDATE feature SET provides_refill = 0")
    con.commit()
    con.close()
    mid = mission(client, mission_body, startIsBase=False)
    for r in client.post(f"/api/missions/{mid}/routes").get_json():
        assert not r["feasible"] and "No refill point available" in r["warnings"]
        assert r["returnFeasibility"]["refillPointName"] is None


def test_stop_outside_routable_area_is_skipped(client, mission_body):
    mid = mission(client, mission_body)
    client.post(f"/api/missions/{mid}/annotations", json={"kind": "SCIENCE_STOP", "lon": 77.21, "lat": 18.21})
    r = client.post(f"/api/missions/{mid}/routes").get_json()[0]
    assert r["feasible"] and any("outside the routable area were skipped" in w for w in r["warnings"])


def test_dust_status_labels():
    from redgrid.services.evaluation import dust_status
    assert [dust_status(v) for v in (None, 0.4, 1.5, 3)] == ["Data unavailable", "Background dust", "Elevated dust",
                                                              "Dust storm conditions"]


def test_weather_is_averaged_over_the_demo_window(app, client):
    con = sqlite3.connect(app.config["DATABASE"])
    con.executemany("INSERT INTO environmental_observation (region_id, sol, observed_at, variable, unit, value, source, data_state) "
                    "VALUES (1,?,?,?,?,?,'MEDA','HISTORICAL_OBSERVATION')",
                    [(5, "2021-02-23T12:00:00Z", "temperature", "C", -40), (6, "2021-02-24T12:00:00Z", "temperature", "C", -50),
                     (6, "2021-02-24T12:00:00Z", "dust_opacity", "", 1.4), (40, "2021-04-01T12:00:00Z", "temperature", "C", 99)])
    con.commit()
    con.close()
    env = client.get(f"/api/regions/1/location?lon={LANDING[0]}&lat={LANDING[1]}").get_json()["environment"]
    assert env["temperature"] == -45.0 and env["dustStatus"] == "Elevated dust" and env["solsWithData"] == 2   # sol 40 is outside


# ------------------------------------------------------------------ CLI and loader
def test_cli_commands(prepared, tmp_path):
    from redgrid import create_app
    data = tmp_path / "data"
    shutil.copytree(prepared[1], data)
    app = create_app({"DATABASE": str(tmp_path / "cli.sqlite3"), "DATA_DIR": str(data)})
    run = app.test_cli_runner()
    assert "Database created" in run.invoke(args=["init-db"]).output
    assert "meets the contract" in run.invoke(args=["check-data"]).output
    out = run.invoke(args=["load-data"]).output
    assert "routable area" in out and "demo window" in out


def test_loader_rejects_bad_files(prepared, tmp_path):
    from redgrid.loader import check_prepared
    data = tmp_path / "data"
    shutil.copytree(prepared[1], data)
    j = data / "jezero"
    assert check_prepared(str(data)) == []
    with rasterio.open(j / "terrain_class.tif", "r+") as ds:          # an invalid class code
        a = ds.read(1)
        a[0, 0] = 9
        ds.write(a, 1)
    (j / "demo_window.json").write_text(json.dumps({"startSol": 0, "endSol": 40, "startUtc": "a", "endUtc": "b", "source": "x"}))
    (j / "vectors" / "routable_area.geojson").write_text(json.dumps({"type": "Polygon", "coordinates": [[[70, 10], [71, 10], [71, 11], [70, 10]]]}))
    (j / "vectors" / "science_targets.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.4, 18.4]}, "properties": {"scienceValue": 2}}]}))
    (j / "hillshade.tif").unlink()
    problems = " | ".join(check_prepared(str(data)))
    for expected in ("terrain_class.tif values", "at most 30 sols", "routable_area", "scienceValue", "missing hillshade.tif"):
        assert expected in problems, expected


def test_loader_loads_meda_manifest_and_extra_points(app, prepared, tmp_path):
    from redgrid.loader import load_prepared
    data = tmp_path / "data"
    shutil.copytree(prepared[1], data)
    j = data / "jezero"
    (j / "meda" / "observations.csv").write_text("sol,observed_at,variable,unit,value,source\n3,2021-02-21T10:00:00Z,pressure,Pa,720,MEDA\n")
    (j / "vectors" / "safe_points.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": list(ll(-500, 500))}, "properties": {"name": "Shelter A", "providesRefill": False}}]}))
    (data / "manifest.json").write_text(json.dumps({"traverse": {"url": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json", "accessedOn": "2026-11-15"}}))
    with app.app_context():
        out = load_prepared(str(data))
    assert any("1 observations" in l for l in out) and any("manifest" in l for l in out)
    con = sqlite3.connect(app.config["DATABASE"])
    names = {r[0] for r in con.execute("SELECT name FROM feature WHERE feature_type='SAFE_POINT'")}
    assert names == {"Ares Base One (concept habitat)", "Shelter A"}            # the seeded base is kept
    assert con.execute("SELECT accessed_on FROM dataset WHERE id=7").fetchone()[0] == "2026-11-15"


def test_load_rejects_and_changes_nothing(app, prepared, tmp_path):
    from redgrid.loader import load_prepared
    data = tmp_path / "data"
    shutil.copytree(prepared[1], data)
    (data / "jezero" / "slope.tif").unlink()
    with app.app_context(), pytest.raises(SystemExit):
        load_prepared(str(data))


# ------------------------------------------------------------------ providers over HTTP
def _serve(flask_app):
    srv = make_server("127.0.0.1", 0, flask_app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def test_http_priority_resolver_and_sensor(prepared, tmp_path, mission_body):
    from redgrid import create_app
    from tools.mock_model_provider import create_app as mock_app
    sensor = Flask("sensor")
    sensor.add_url_rule("/v1/health", "health", lambda: jsonify({"status": "READY", "name": "suit-sim", "version": "1", "kind": "SENSOR"}))
    sensor.add_url_rule("/v1/missions/<int:mid>/resources", "res", lambda mid: jsonify({"values": [
        {"variable": "OXYGEN_KG", "value": 0.55, "unit": "kg", "observedAt": "2026-11-15T08:00:00Z"},
        {"variable": "NOT_A_VARIABLE", "value": 1, "unit": "x"}]}))
    s1, model_url = _serve(mock_app())
    s2, sensor_url = _serve(sensor)
    try:
        db = tmp_path / "http.sqlite3"
        shutil.copy(prepared[0], db)
        c = create_app({"DATABASE": str(db), "DATA_DIR": str(prepared[1]), "PRIORITY_RESOLVERS": ["model", "algorithm"],
                        "MODEL_PRIORITY_URL": model_url, "SENSOR_URL": sensor_url}).test_client()
        prov = c.get("/api/providers").get_json()
        assert prov["priority"][0]["status"] == "READY" and prov["resource"][0]["status"] == "READY"
        mid = c.post("/api/missions", json=mission_body).get_json()["id"]
        res = c.get(f"/api/missions/{mid}/resources").get_json()
        assert res["oxygenKg"]["source"] == "SENSOR" and res["batteryWh"]["source"] == "DEFAULT_ASSUMPTION"
        c.put(f"/api/missions/{mid}/resources", json={"oxygenKg": 0.7})
        assert c.get(f"/api/missions/{mid}/resources").get_json()["oxygenKg"]["source"] == "USER_INPUT"   # user wins over sensor
        r = c.post(f"/api/missions/{mid}/routes").get_json()[3]
        assert r["priorityResolver"]["kind"] == "MODEL"
    finally:
        s1.shutdown()
        s2.shutdown()


def test_chain_and_contract_failures():
    from redgrid.providers import arrays
    from redgrid.providers.chain import ProviderChain
    from redgrid.providers.contracts import (CostFactors, GroupScales, ProviderError, ProviderInfo, validate_cost_factors,
                                             validate_group_scales)

    class Broken:
        def info(self): return ProviderInfo("broken", "ALGORITHM", "LOCAL", "1")
        def is_ready(self): return True
        def resolve(self, *_): raise ValueError("boom")
    with pytest.raises(RuntimeError, match="no provider answered"):
        ProviderChain("x", [Broken()]).call("resolve", None)
    with pytest.raises(ValueError):
        ProviderChain("x", [])
    with pytest.raises(ValueError):
        arrays.encode(np.zeros(3, np.int64))
    with pytest.raises(ValueError):
        arrays.decode({"dtype": "uint32", "encoding": "raw", "shape": [1], "data": ""})
    info = ProviderInfo("m", "MODEL", "HTTP", "1")
    req = type("Q", (), {"height": 2, "width": 2, "routable": np.ones((2, 2), bool)})()
    for f in (CostFactors(info, np.zeros((6, 2, 2)), 0.4, groups=["HAZARD"]), CostFactors(info, np.zeros((6, 3, 2)), 0.4),
              CostFactors(info, np.zeros((6, 2, 2)), 0.0)):
        with pytest.raises(ProviderError):
            validate_cost_factors(f, req)
    for bad in (dict(hazard=-1), dict(uncertainty=0.5), dict(distance_weight=2)):
        kw = dict(hazard=1, terrain=1, science=1, communication=1, uncertainty=1, rover_path=1, distance_weight=0.5) | bad
        with pytest.raises(ProviderError):
            validate_group_scales(GroupScales(info, **kw))


# ------------------------------------------------------------------ repositories used by the training package
def test_training_repository_methods(app):
    from redgrid.db import connect
    from redgrid.models import CategoryWeight, CostModel
    from redgrid.providers.cost import AlgorithmCostProvider
    from redgrid.repositories.catalog import CostModelRepository, DatasetRepository, TerrainClassRepository
    con = connect(app.config["DATABASE"])
    cm = CostModelRepository(con)
    weights = [CategoryWeight(w.category_key, 0.1, 2.0 if w.category_key in ("no_comm", "hazard_0_50") else w.weight, 0.5, 0.01,
                              "LEARNED" if w.basis == "PLACEHOLDER" else w.basis) for w in cm.get_active().weights]
    m = cm.save(CostModel(0, 0, "CONDITIONAL_LOGIT", "DRAFT", "2026-11-15", "test", 0.7, "2026-11-15T00:00:00Z"), weights)
    assert m.version == 1 and m.status == "DRAFT"
    cm.activate(m.id)
    assert cm.get_active().version == 1 and cm.get_by_version(0).status == "RETIRED"
    eff = AlgorithmCostProvider(cm).effective_weights()
    assert eff["hazard_0_50"] == 2.0 and eff["no_comm"] == 1.5           # FIXED category keeps its version 0 weight
    assert TerrainClassRepository(con).class_of("Aeb") == "SAND" and TerrainClassRepository(con).class_of("zz") is None
    ds = DatasetRepository(con)
    assert len(ds.get_all()) == 12 and ds.get_by_id(5).doi == "10.3133/sim3464"
    from redgrid.errors import ApiError
    with pytest.raises(ApiError):
        ds.get_by_id(99)
    con.close()


def test_raster_sample_and_models(app):
    from redgrid.db import connect
    from redgrid.models import PriorityProfile, Region, RouteProfile, ProfileRule
    from redgrid.geo import BBox
    from redgrid.repositories.catalog import LayerRepository
    from redgrid.repositories.raster import RasterRepository
    rr = RasterRepository(app.config["DATA_DIR"], LayerRepository(connect(app.config["DATABASE"])))
    assert -3000 < rr.sample(1, "elevation", *LANDING) < -2000
    assert rr.sample(1, "elevation", 77.21, 18.21) is None              # outside the prepared file
    assert not Region(1, "x", BBox(0, 0, 1, 1), "", 0, 0, 1, None).is_routable(0.5, 0.5)
    from redgrid.errors import ApiError
    with pytest.raises(ApiError):
        PriorityProfile.from_dict({k: "a" for k in ["safetyWeight", "scienceWeight", "distanceWeight", "walkingDifficultyWeight",
                                                    "returnWeight", "environmentWeight", "roverPathWeight"]})
    bad = RouteProfile("SAFEST", "x", 2.0, [ProfileRule("SAFEST", "HAZARD", 1, 50, None)])
    assert bad.validate() is False


def test_unexpected_error_is_a_clean_500(app, monkeypatch):
    from redgrid.services.catalog_service import CatalogService
    monkeypatch.setattr(CatalogService, "regions_json", lambda self: 1 / 0)
    r = app.test_client().get("/api/regions")
    assert r.status_code == 500 and r.get_json()["error"]["code"] == "INTERNAL_ERROR"


def test_download_script_lists_offline():
    import subprocess, sys
    out = subprocess.run([sys.executable, "tools/download_redgrid_data.py", "--list"], capture_output=True, text=True, check=True).stdout
    assert "hirise_dtm" in out and "apollo14" in out
    bad = subprocess.run([sys.executable, "tools/download_redgrid_data.py", "--only", "nope"], capture_output=True, text=True)
    assert bad.returncode == 2


def _set_cap(app, value):
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute("UPDATE planning_constant SET value = ? WHERE key = 'max_corridor_cells'", (value,))
    con.commit()
    con.close()


def test_corridor_cap_refuses_a_trip_too_long(app, client, mission_body):
    _set_cap(app, 10000)
    mid = mission(client, mission_body)
    r = client.post(f"/api/missions/{mid}/routes")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "ROUTE_TOO_LONG"
    assert r.get_json()["error"]["details"]["limit"] == 10000


def test_corridor_cap_stops_widening_with_a_warning(app, client, mission_body):
    s, d = ll(-300, 0), ll(300, 0)
    mid = mission(client, mission_body, startLon=s[0], startLat=s[1], destLon=d[0], destLat=d[1])
    for north in range(-1400, 1401, 140):          # the same 2.8 km wall: needs widening to get round
        lon, lat = ll(0, north)
        client.post(f"/api/missions/{mid}/annotations", json={"kind": "HAZARD_WARNING", "lon": lon, "lat": lat,
                                                               "severity": "HIGH", "radiusM": 100})
    first = client.post(f"/api/missions/{mid}/routes").get_json()[1]
    _set_cap(app, 200000)                           # allows the first corridor (~2 km) but not a widened one
    r = client.post(f"/api/missions/{mid}/routes/recalculate").get_json()[1]
    assert not r["feasible"] and any("size limit" in w for w in r["warnings"])
    assert first["feasible"]                         # with the normal cap, widening found the way round


# ------------------------------------------------------------------ puzzle pieces checked at start-up
class IncompleteRouteRepository:          # forgot replace_all and get_by_id
    def __init__(self, db):
        self.db = db

    def get_by_mission(self, mission_id):
        return []


def test_startup_rejects_a_piece_with_missing_methods(prepared):
    from redgrid import create_app
    with pytest.raises(RuntimeError) as e:
        create_app({"DATABASE": str(prepared[0]), "DATA_DIR": str(prepared[1]),
                    "REPOSITORY_OVERRIDES": {"routes": IncompleteRouteRepository}})
    assert "replace_all" in str(e.value) and "get_by_id" in str(e.value)


def test_startup_rejects_bad_configuration(prepared):
    from redgrid import create_app
    for cfg, text in (({"REPOSITORY_OVERRIDES": {"rutes": "x.Y"}}, "unknown repository slot"),
                      ({"REPOSITORY_OVERRIDES": {"routes": "nowhere.Missing"}}, "cannot load"),
                      ({"COST_PROVIDERS": ["model"]}, "last provider must be local"),
                      ({"PRIORITY_RESOLVERS": ["magic", "algorithm"]}, "unknown provider")):
        with pytest.raises(RuntimeError, match=text):
            create_app({"DATABASE": str(prepared[0]), "DATA_DIR": str(prepared[1]), **cfg})


def test_a_complete_replacement_piece_is_used(prepared, tmp_path, mission_body):
    """A subclass that keeps the interface is accepted and actually used by the app."""
    from redgrid import create_app
    from redgrid.repositories.route import RouteRepository
    calls = []

    class CountingRouteRepository(RouteRepository):
        def replace_all(self, mission_id, routes):
            calls.append(mission_id)
            return super().replace_all(mission_id, routes)
    db = tmp_path / "swap.sqlite3"
    shutil.copy(prepared[0], db)
    c = create_app({"DATABASE": str(db), "DATA_DIR": str(prepared[1]),
                    "REPOSITORY_OVERRIDES": {"routes": CountingRouteRepository}}).test_client()
    mid = c.post("/api/missions", json=mission_body).get_json()["id"]
    assert len(c.post(f"/api/missions/{mid}/routes").get_json()) == 4 and calls == [mid]
