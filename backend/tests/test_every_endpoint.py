"""Calls EVERY endpoint the app exposes with valid and invalid dummy data, plus edge cases.
test_every_endpoint_is_called fails if a new endpoint is added without being exercised here."""
import json

import pytest

from conftest import LANDING, ll

CALLED: set = set()


def call(client, method, url, **kw):
    r = client.open(url, method=method, **kw)
    rule = client.application.url_map.bind("localhost").match(url.split("?")[0], method=method, return_rule=True)[0].rule
    CALLED.add((method, rule))
    return r


def code(r):
    return r.get_json()["error"]["code"]


@pytest.fixture
def m(client, mission_body):
    return call(client, "POST", "/api/missions", json=mission_body).get_json()


# ------------------------------------------------------------------ catalog: valid
def test_catalog_valid(client):
    assert call(client, "GET", "/api/health").get_json()["status"] == "ok"
    regions = call(client, "GET", "/api/regions").get_json()
    assert len(regions) == 1 and regions[0]["name"] == "Jezero Crater"
    assert call(client, "GET", "/api/regions/1").status_code == 200
    layers = call(client, "GET", "/api/regions/1/layers").get_json()
    assert len(layers) == 18 and all({"key", "kind", "dataState", "dataset"} <= set(l) for l in layers)
    for l in layers:
        if l["kind"] == "VECTOR":                       # every vector layer, empty or not, returns a FeatureCollection
            gj = call(client, "GET", f"/api/regions/1/layers/{l['key']}/geojson").get_json()
            assert gj["type"] == "FeatureCollection"
            for f in gj["features"]:
                assert set(f["properties"]) == {"id", "featureType", "name", "code", "scienceValue", "providesRefill", "heightM"}
    ds = call(client, "GET", "/api/regions/1/datasets").get_json()
    assert ds and all("url" in d for d in ds)
    for path in ("/api/route-profiles", "/api/priority-presets", "/api/categories", "/api/terrain-class-mapping",
                 "/api/cost-model", "/api/cost-models", "/api/planning-constants", "/api/demo-window", "/api/providers"):
        r = call(client, "GET", path)
        assert r.status_code == 200 and r.get_json() is not None, path
    assert call(client, "GET", "/api/cost-models/1").get_json()["weights"]


def test_terrain_every_raster_layer(client):
    """Prepared rasters return data; rasters the demo does not prepare give DATA_NOT_PREPARED, never a crash."""
    assert call(client, "GET", "/api/regions/1/terrain").status_code == 200          # whole region, no bbox
    w, s = ll(-500, -500)
    e, n = ll(500, 500)
    q = f"west={w}&south={s}&east={e}&north={n}"
    for layer in ("hillshade", "slope", "roughness", "terrain_class", "comm_coverage", "elevation"):
        r = call(client, "GET", f"/api/regions/1/terrain/texture?{q}&size=256&layer={layer}")
        assert r.status_code == 200 and r.mimetype == "image/png", layer
    for layer in ("thermal_inertia", "imagery_hirise", "imagery_ctx", "elevation_ctx"):
        assert code(call(client, "GET", f"/api/regions/1/terrain/texture?{q}&layer={layer}")) == "DATA_NOT_PREPARED"
    t = call(client, "GET", f"/api/regions/1/terrain?{q}&maxSize=16").get_json()
    assert t["width"] <= 16 and t["minElevationM"] < t["maxElevationM"]
    far = call(client, "GET", "/api/regions/1/terrain?west=77.21&south=18.21&east=77.22&north=18.22&maxSize=16").get_json()
    assert far["dataState"] == "DATA_UNAVAILABLE" and all(v is None for v in far["elevations"])


# ------------------------------------------------------------------ catalog: invalid
@pytest.mark.parametrize("url,expected", [
    ("/api/regions/2", "REGION_NOT_FOUND"),
    ("/api/regions/2/layers", "REGION_NOT_FOUND"),
    ("/api/regions/2/datasets", "REGION_NOT_FOUND"),
    ("/api/regions/1/layers/nope/geojson", "LAYER_NOT_FOUND"),
    ("/api/regions/1/layers/elevation/geojson", "LAYER_NOT_VECTOR"),
    ("/api/regions/1/terrain/texture?layer=rover_path", "LAYER_NOT_RASTER"),
    ("/api/regions/1/terrain/texture?layer=nope", "LAYER_NOT_FOUND"),
    ("/api/regions/1/terrain/texture?size=10", "VALIDATION_ERROR"),
    ("/api/regions/1/terrain/texture?size=abc", "VALIDATION_ERROR"),
    ("/api/regions/1/terrain?maxSize=9999", "VALIDATION_ERROR"),
    ("/api/regions/1/terrain?west=77.3", "VALIDATION_ERROR"),
    ("/api/regions/1/terrain?west=77.5&south=18.3&east=77.4&north=18.4", "VALIDATION_ERROR"),
    ("/api/regions/1/terrain?west=77.0&south=18.3&east=77.4&north=18.4", "OUT_OF_REGION"),
    ("/api/cost-models/99", "COST_MODEL_NOT_FOUND"),
    ("/api/regions/1/location?lon=abc&lat=18.4", "VALIDATION_ERROR"),
    ("/api/regions/1/location?lat=18.4", "VALIDATION_ERROR"),
    ("/api/regions/1/location?lon=77.0&lat=18.4", "OUT_OF_REGION"),
    ("/api/regions/2/location?lon=77.4&lat=18.4", "REGION_NOT_FOUND"),
    ("/api/nope", "NOT_FOUND"),
])
def test_catalog_invalid(client, url, expected):
    r = client.get(url)
    assert code(r) == expected and set(r.get_json()["error"]) == {"code", "message", "details"}


def test_location_everywhere(client):
    """Inside the routable area, inside the data but outside it, outside the data, and at a refill point."""
    for (e, n), routable in (((0, 0), True), ((-1500, 900), True), ((40000, 40000), False)):
        lon, lat = ll(e, n)
        if not (77.2 <= lon <= 77.7 and 18.2 <= lat <= 18.7):
            continue
        r = call(client, "GET", f"/api/regions/1/location?lon={lon}&lat={lat}").get_json()
        assert r["routable"] is routable
        assert r["environment"]["regionId"] == 1
    corner = call(client, "GET", "/api/regions/1/location?lon=77.2&lat=18.2").get_json()   # edge of the region box
    assert corner["routable"] is False and corner["dataQuality"] == "Unavailable"


# ------------------------------------------------------------------ missions: every field, valid and invalid
def test_mission_crud_valid(client, mission_body):
    for profile in ("BALANCED", "SAFETY_FOCUSED", "SCIENCE_FOCUSED", "SHORTEST"):
        r = call(client, "POST", "/api/missions", json={**mission_body, "profile": profile})
        assert r.status_code == 201 and abs(sum(r.get_json()["priorities"].values()) - 1) < 1e-6
    custom = {**mission_body, "profile": "CUSTOM", "objective": "x" * 500, "reserveFraction": 0.35, "startIsBase": False,
              "priorities": {"safetyWeight": 5, "scienceWeight": 3, "distanceWeight": 1, "walkingDifficultyWeight": 1,
                             "returnWeight": 0, "environmentWeight": 0, "roverPathWeight": 0},
              "priorityMix": [{"presetKey": "SAFETY_FOCUSED", "percent": 100}],
              "resources": {"oxygenKg": 0.9, "batteryWh": 900, "metabolicRateW": 280, "suitPowerW": 85}}
    c = call(client, "POST", "/api/missions", json=custom).get_json()
    assert c["priorities"]["safetyWeight"] == 0.5 and c["priorityMix"][0]["percent"] == 100 and c["startIsBase"] is False
    mid = c["id"]
    assert call(client, "GET", f"/api/missions/{mid}").get_json()["reserveFraction"] == 0.35
    assert len(call(client, "GET", "/api/missions").get_json()) == 5
    assert all(x["status"] == "DRAFT" for x in call(client, "GET", "/api/missions?status=DRAFT").get_json())
    p = call(client, "PATCH", f"/api/missions/{mid}", json={"name": "Renamed", "objective": None, "startIsBase": True,
                                                             "resources": {"oxygenKg": 1.0}}).get_json()
    assert p["name"] == "Renamed" and p["objective"] is None and p["startIsBase"] is True
    e, n = ll(-800, 400)
    p = call(client, "PATCH", f"/api/missions/{mid}", json={"destLon": e, "destLat": n}).get_json()
    assert p["destLon"] == e
    p = call(client, "PATCH", f"/api/missions/{mid}", json={"profile": "CUSTOM", "priorityMix": [
        {"presetKey": "BALANCED", "percent": 50}, {"presetKey": "SHORTEST", "percent": 50}]}).get_json()
    assert p["priorities"]["distanceWeight"] == pytest.approx(0.325)
    assert call(client, "GET", f"/api/missions/{mid}/resources").get_json()["oxygenKg"]["value"] == 1.0


@pytest.mark.parametrize("over,expected", [
    ({"regionId": "1"}, "VALIDATION_ERROR"), ({"regionId": 7}, "REGION_NOT_FOUND"), ({"name": None}, "VALIDATION_ERROR"),
    ({"name": 5}, "VALIDATION_ERROR"), ({"name": "x" * 81}, "VALIDATION_ERROR"), ({"objective": "x" * 501}, "VALIDATION_ERROR"),
    ({"startLon": "77.4"}, "VALIDATION_ERROR"), ({"startLon": None}, "VALIDATION_ERROR"), ({"destLat": True}, "VALIDATION_ERROR"),
    ({"startLon": 80.0}, "OUT_OF_REGION"), ({"destLon": 77.21, "destLat": 18.21}, "OUT_OF_COVERAGE"),
    ({"profile": "FASTEST"}, "VALIDATION_ERROR"), ({"profile": None}, "VALIDATION_ERROR"),
    ({"priorities": {"safetyWeight": 1}}, "INVALID_PROFILE"),                         # priorities with a preset
    ({"profile": "CUSTOM"}, "INVALID_PROFILE"),                                        # nothing to build from
    ({"profile": "CUSTOM", "priorities": "a"}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorities": {"safetyWeight": 1}}, "INVALID_PROFILE"),     # missing weights
    ({"profile": "CUSTOM", "priorities": dict.fromkeys(["safetyWeight", "scienceWeight", "distanceWeight", "walkingDifficultyWeight",
                                                          "returnWeight", "environmentWeight", "roverPathWeight"], 0)}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorities": dict.fromkeys(["safetyWeight", "scienceWeight", "distanceWeight", "walkingDifficultyWeight",
                                                          "returnWeight", "environmentWeight", "roverPathWeight"], -1)}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorityMix": "a"}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorityMix": [{"presetKey": "CUSTOM", "percent": 100}]}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorityMix": [{"presetKey": "BALANCED", "percent": 50}, {"presetKey": "BALANCED", "percent": 50}]}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorityMix": [{"presetKey": "BALANCED", "percent": 0}, {"presetKey": "SHORTEST", "percent": 100}]}, "INVALID_PROFILE"),
    ({"profile": "CUSTOM", "priorityMix": [{"presetKey": "BALANCED", "percent": 99.9}]}, "INVALID_PROFILE"),
    ({"reserveFraction": -0.1}, "VALIDATION_ERROR"), ({"reserveFraction": 1}, "VALIDATION_ERROR"),
    ({"startIsBase": "yes"}, "VALIDATION_ERROR"), ({"resources": []}, "VALIDATION_ERROR"),
    ({"resources": {"oxygenKg": -1}}, "VALIDATION_ERROR"), ({"resources": {"batteryWh": "a"}}, "VALIDATION_ERROR"),
])
def test_create_invalid(client, mission_body, over, expected):
    r = client.post("/api/missions", json={**mission_body, **over})
    assert r.status_code >= 400 and code(r) == expected, (over, r.get_json())


@pytest.mark.parametrize("raw,ctype", [(b"{bad json", "application/json"), (b"[1,2]", "application/json"), (b"null", "application/json")])
def test_malformed_bodies(client, raw, ctype):
    assert code(client.post("/api/missions", data=raw, content_type=ctype)) == "VALIDATION_ERROR"


def test_mission_actions_and_errors(client, m):
    mid = m["id"]
    assert code(call(client, "GET", "/api/missions/999")) == "MISSION_NOT_FOUND"
    assert code(call(client, "PATCH", "/api/missions/999", json={"name": "x"})) == "MISSION_NOT_FOUND"
    assert code(client.get("/api/missions?status=DONE")) == "VALIDATION_ERROR"
    assert code(client.patch(f"/api/missions/{mid}", json={"profile": "X"})) == "VALIDATION_ERROR"
    assert code(client.patch(f"/api/missions/{mid}", json={"startLon": 77.21, "startLat": 18.21})) == "OUT_OF_COVERAGE"
    assert code(client.patch(f"/api/missions/{mid}", json={"name": ""})) == "VALIDATION_ERROR"
    assert client.get(f"/api/missions/{mid}").get_json()["name"] == "Delta walk"     # failed PATCH changed nothing
    d = call(client, "POST", f"/api/missions/{mid}/duplicate")
    assert d.status_code == 201 and code(client.post("/api/missions/999/duplicate")) == "MISSION_NOT_FOUND"
    assert code(call(client, "PATCH", f"/api/missions/{mid}/status", json={})) == "VALIDATION_ERROR"
    assert code(client.patch(f"/api/missions/{mid}/status", json={"status": "DRAFT"})) == "INVALID_STATUS_TRANSITION"
    assert client.patch(f"/api/missions/{mid}/status", json={"status": "PLANNED"}).get_json()["status"] == "PLANNED"
    assert client.patch(f"/api/missions/{mid}/status", json={"status": "DRAFT"}).get_json()["status"] == "DRAFT"


def test_annotations_and_resources(client, m):
    mid = m["id"]
    lon, lat = ll(-1000, 0)
    ok = [{"kind": "SCIENCE_STOP", "lon": lon, "lat": lat, "durationMin": 15, "note": "n"},
          {"kind": "SCIENCE_STOP", "lon": lon, "lat": lat},
          {"kind": "HAZARD_WARNING", "lon": lon, "lat": lat, "severity": "LOW", "radiusM": 20}]
    ids = [call(client, "POST", f"/api/missions/{mid}/annotations", json=a).get_json()["id"] for a in ok]
    assert len(call(client, "GET", f"/api/missions/{mid}/annotations").get_json()) == 3
    bad = [({"kind": "NOTE", "lon": lon, "lat": lat}, "VALIDATION_ERROR"),
           ({"kind": "SCIENCE_STOP", "lon": 80, "lat": lat}, "OUT_OF_REGION"),
           ({"kind": "SCIENCE_STOP", "lat": lat}, "VALIDATION_ERROR"),
           ({"kind": "SCIENCE_STOP", "lon": lon, "lat": lat, "durationMin": 0}, "VALIDATION_ERROR"),
           ({"kind": "SCIENCE_STOP", "lon": lon, "lat": lat, "severity": "LOW"}, "VALIDATION_ERROR"),
           ({"kind": "HAZARD_WARNING", "lon": lon, "lat": lat, "radiusM": 20}, "VALIDATION_ERROR"),
           ({"kind": "HAZARD_WARNING", "lon": lon, "lat": lat, "severity": "LOW", "radiusM": -5}, "VALIDATION_ERROR"),
           ({"kind": "HAZARD_WARNING", "lon": lon, "lat": lat, "severity": "LOW"}, "VALIDATION_ERROR")]
    for body, expected in bad:
        assert code(client.post(f"/api/missions/{mid}/annotations", json=body)) == expected, body
    assert call(client, "DELETE", f"/api/missions/{mid}/annotations/{ids[0]}").status_code == 204
    assert code(client.delete(f"/api/missions/{mid}/annotations/99999")) == "ANNOTATION_NOT_FOUND"
    assert code(client.get("/api/missions/999/annotations")) == "MISSION_NOT_FOUND"
    r = call(client, "GET", f"/api/missions/{mid}/resources").get_json()
    assert {r[k]["source"] for k in ("oxygenKg", "batteryWh", "metabolicRateW", "suitPowerW")} == {"DEFAULT_ASSUMPTION"}
    r = call(client, "PUT", f"/api/missions/{mid}/resources", json={"oxygenKg": 0.5, "suitPowerW": 70, "startIsBase": False}).get_json()
    assert r["oxygenKg"]["source"] == "USER_INPUT" and r["suitPowerW"]["value"] == 70 and r["startIsBase"] is False
    assert code(client.put(f"/api/missions/{mid}/resources", json={"reserveFraction": 2})) == "VALIDATION_ERROR"
    assert code(client.put(f"/api/missions/{mid}/resources", data=b"[]", content_type="application/json")) == "VALIDATION_ERROR"
    assert code(client.get("/api/missions/999/resources")) == "MISSION_NOT_FOUND"


# ------------------------------------------------------------------ routes and report
def test_routes_select_report(client, m):
    mid = m["id"]
    assert call(client, "GET", f"/api/missions/{mid}/routes").get_json() == []
    assert code(call(client, "GET", f"/api/missions/{mid}/report")) == "ROUTES_NOT_CALCULATED"
    routes = call(client, "POST", f"/api/missions/{mid}/routes").get_json()
    assert len(routes) == 4 and json.loads(json.dumps(routes)) == routes                 # plain JSON, no numpy leftovers
    assert call(client, "GET", f"/api/missions/{mid}/routes").get_json() == routes        # stored exactly as returned
    for bad, expected in (({"routeId": "1"}, "VALIDATION_ERROR"), ({}, "VALIDATION_ERROR"), ({"routeId": 99999}, "ROUTE_NOT_FOUND")):
        assert code(call(client, "PUT", f"/api/missions/{mid}/selected-route", json=bad)) == expected
    rid = routes[2]["id"]
    client.put(f"/api/missions/{mid}/selected-route", json={"routeId": rid})
    rep = client.get(f"/api/missions/{mid}/report").get_json()
    assert rep["recommendedRoute"]["id"] == rid
    assert set(rep) == {"mission", "routes", "recommendedRoute", "annotations", "sources", "costModel", "trainingSources", "providersUsed",
                        "constants", "terrainClassMapping", "demoWindow", "resources", "caveats", "notice"}
    re = call(client, "POST", f"/api/missions/{mid}/routes/recalculate").get_json()
    assert {r["id"] for r in re}.isdisjoint({r["id"] for r in routes})                   # new ids every time
    assert code(client.post("/api/missions/999/routes")) == "MISSION_NOT_FOUND"
    assert code(client.get("/api/missions/999/report")) == "MISSION_NOT_FOUND"


def test_edge_start_equals_destination(client, mission_body):
    body = {**mission_body, "destLon": mission_body["startLon"], "destLat": mission_body["startLat"]}
    mid = client.post("/api/missions", json=body).get_json()["id"]
    for r in client.post(f"/api/missions/{mid}/routes").get_json():
        assert len(r["geometry"]["coordinates"]) >= 2 and r["distanceM"] == 0 and r["feasible"]


def test_edge_stop_on_blocked_ground_is_skipped(app, client, mission_body):
    import rasterio
    import numpy as np
    from redgrid.geo import eqc_to_lonlat
    with rasterio.open(f"{app.config['DATA_DIR']}/jezero/slope.tif") as ds:
        a = ds.read(1)
        r, c = np.argwhere(a > 25)[0]
        x, y = ds.xy(int(r), int(c))
    lon, lat = (float(v) for v in eqc_to_lonlat(x, y))
    mid = client.post("/api/missions", json=mission_body).get_json()["id"]
    client.post(f"/api/missions/{mid}/annotations", json={"kind": "SCIENCE_STOP", "lon": lon, "lat": lat, "durationMin": 600})
    routes = client.post(f"/api/missions/{mid}/routes").get_json()
    assert all(r["feasible"] for r in routes)
    assert any("science stop(s) on blocked ground" in w for w in routes[0]["warnings"])
    assert routes[0]["durationMin"] < 600                                              # skipped stop adds no time


def test_edge_zero_and_huge_resources(client, mission_body):
    z = client.post("/api/missions", json={**mission_body, "resources": {"oxygenKg": 0, "batteryWh": 0}}).get_json()["id"]
    for r in client.post(f"/api/missions/{z}/routes").get_json():
        assert r["feasible"] is False and r["overallRisk"] == "CRITICAL"
    h = client.post("/api/missions", json={**mission_body, "reserveFraction": 0, "resources": {"oxygenKg": 50, "batteryWh": 99999}}).get_json()["id"]
    for r in client.post(f"/api/missions/{h}/routes").get_json():
        assert r["feasible"] and r["returnFeasibility"]["limitingResource"] == "NONE"


def test_edge_high_warning_on_start(client, mission_body):
    mid = client.post("/api/missions", json=mission_body).get_json()["id"]
    client.post(f"/api/missions/{mid}/annotations", json={"kind": "HAZARD_WARNING", "lon": LANDING[0], "lat": LANDING[1],
                                                           "severity": "HIGH", "radiusM": 50})
    for r in client.post(f"/api/missions/{mid}/routes").get_json():
        assert r["feasible"] is False and r["missionMatch"] == 0 and "blocked ground" in r["returnFeasibility"]["reason"]


def test_finalized_mission_is_read_only(client, m):
    mid = m["id"]
    client.post(f"/api/missions/{mid}/routes")
    client.patch(f"/api/missions/{mid}/status", json={"status": "PLANNED"})
    client.patch(f"/api/missions/{mid}/status", json={"status": "FINALIZED"})
    lon, lat = ll(-100, 0)
    for method, url, body in (("PATCH", f"/api/missions/{mid}", {"name": "x"}), ("POST", f"/api/missions/{mid}/annotations",
                              {"kind": "SCIENCE_STOP", "lon": lon, "lat": lat}), ("PUT", f"/api/missions/{mid}/resources", {"oxygenKg": 1}),
                              ("POST", f"/api/missions/{mid}/routes/recalculate", None)):
        assert code(client.open(url, method=method, json=body)) == "MISSION_FINALIZED", url
    assert client.get(f"/api/missions/{mid}/report").status_code == 200                 # still readable


def test_no_prepared_data(tmp_path):
    """A fresh database with no prepared files: catalog works, routing parts answer DATA_NOT_PREPARED, nothing crashes."""
    from redgrid import create_app, db
    f = tmp_path / "empty.sqlite3"
    db.init_db(str(f))
    c = create_app({"DATABASE": str(f), "DATA_DIR": str(tmp_path / "nodata")}).test_client()
    assert c.get("/api/regions/1").get_json()["routableArea"] is None
    assert c.get(f"/api/regions/1/location?lon={LANDING[0]}&lat={LANDING[1]}").get_json()["routable"] is False
    assert code(c.get("/api/regions/1/terrain")) == "DATA_NOT_PREPARED"
    assert code(c.get("/api/regions/1/terrain/texture")) == "DATA_NOT_PREPARED"
    body = {"regionId": 1, "name": "x", "startLon": LANDING[0], "startLat": LANDING[1], "destLon": 77.44, "destLat": 18.45, "profile": "BALANCED"}
    assert code(c.post("/api/missions", json=body)) == "DATA_NOT_PREPARED"


def test_every_endpoint_is_called(app):
    """Runs last in this file: every URL rule of the app must have been called above."""
    rules = {(m, r.rule) for r in app.url_map.iter_rules() if r.rule.startswith("/api")
             for m in r.methods - {"HEAD", "OPTIONS"}}
    missing = rules - CALLED
    assert not missing, f"endpoints never called: {sorted(missing)}"
