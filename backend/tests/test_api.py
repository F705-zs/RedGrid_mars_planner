import pytest

from conftest import LANDING, ll

ROUTE_FIELDS = {"id", "missionId", "routeType", "geometry", "elevationProfile", "feasible", "overallRisk", "missionMatch", "distanceM",
                "durationMin", "averageSlopeDeg", "maxSlopeDeg", "elevationGainM", "elevationLossM", "terrainDifficulty", "hazardCount",
                "scienceScore", "oxygenUsedKg", "batteryUsedWh", "oxygenLeftKg", "batteryLeftWh", "costModelId", "costModelVersion",
                "costProvider", "priorityResolver", "window", "calculatedAt", "assessment", "returnFeasibility", "warnings", "recommendation"}


def err(r):
    return r.get_json()["error"]["code"]


def create(client, body, **over):
    r = client.post("/api/missions", json={**body, **over})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ---------------------------------------------------------------- catalog
def test_catalog_endpoints(client):
    reg = client.get("/api/regions/1").get_json()
    assert reg["bboxWest"] == 77.2 and reg["routableArea"]["type"] == "Polygon"
    assert len(client.get("/api/route-profiles").get_json()) == 4
    assert all(len(p["rules"]) == 6 for p in client.get("/api/route-profiles").get_json())
    presets = client.get("/api/priority-presets").get_json()
    assert [p["key"] for p in presets] == ["BALANCED", "SAFETY_FOCUSED", "SCIENCE_FOCUSED", "SHORTEST"]
    assert all(abs(sum(p["weights"].values()) - 1) < 1e-6 for p in presets)
    assert len(client.get("/api/categories").get_json()) == 18
    assert len(client.get("/api/terrain-class-mapping").get_json()) == 15
    m = client.get("/api/cost-model").get_json()
    assert m["version"] == 0 and {w["basis"] for w in m["weights"]} == {"REFERENCE", "PHYSICS_IN_BASE", "PLACEHOLDER"}
    assert len(client.get("/api/planning-constants").get_json()) == 38
    assert client.get("/api/demo-window").get_json()["dataState"] == "DEMONSTRATION_DATA"
    prov = client.get("/api/providers").get_json()
    assert prov["cost"][-1]["kind"] == "ALGORITHM" and prov["resource"][-1]["kind"] == "DEFAULTS"
    gj = client.get("/api/regions/1/layers/safe_points/geojson").get_json()
    assert gj["features"][0]["properties"]["providesRefill"] is True
    assert err(client.get("/api/regions/1/layers/slope/geojson")) == "LAYER_NOT_VECTOR"
    assert err(client.get("/api/regions/1/terrain/texture?layer=hazards")) == "LAYER_NOT_RASTER"
    assert err(client.get("/api/regions/9")) == "REGION_NOT_FOUND"


def test_terrain_and_texture(client):
    w, s = ll(-1000, -1000)
    e, n = ll(1000, 1000)
    t = client.get(f"/api/regions/1/terrain?west={w}&south={s}&east={e}&north={n}&maxSize=64").get_json()
    assert t["width"] <= 64 and len(t["elevations"]) == t["width"] * t["height"]
    r = client.get(f"/api/regions/1/terrain/texture?west={w}&south={s}&east={e}&north={n}&size=256&layer=terrain_class")
    assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert err(client.get("/api/regions/1/terrain?west=70&south=10&east=71&north=11")) == "OUT_OF_REGION"


def test_location(client):
    loc = client.get(f"/api/regions/1/location?lon={LANDING[0]}&lat={LANDING[1]}").get_json()
    assert loc["routable"] is True and loc["terrainClass"] in ("REGOLITH", "BEDROCK", "SAND", "BOULDER_FIELD")
    assert loc["nearestRefillPoint"]["name"].startswith("Ares Base One") and loc["distanceToNearestRefillPointM"] < 1
    assert loc["environment"]["dataState"] == "DATA_UNAVAILABLE"           # no MEDA in the demo: never invented
    out = client.get("/api/regions/1/location?lon=77.25&lat=18.25").get_json()
    assert out["routable"] is False and out["slopeDeg"] is None
    assert err(client.get("/api/regions/1/location?lon=80&lat=18.4")) == "OUT_OF_REGION"


# ---------------------------------------------------------------- missions
def test_create_validations(client, mission_body):
    assert err(client.post("/api/missions", json={**mission_body, "destLon": 80.0})) == "OUT_OF_REGION"
    assert err(client.post("/api/missions", json={**mission_body, "destLon": 77.25, "destLat": 18.25})) == "OUT_OF_COVERAGE"
    assert err(client.post("/api/missions", json={**mission_body, "profile": "CUSTOM"})) == "INVALID_PROFILE"
    bad_mix = [{"presetKey": "BALANCED", "percent": 50}, {"presetKey": "SHORTEST", "percent": 40}]
    assert err(client.post("/api/missions", json={**mission_body, "profile": "CUSTOM", "priorityMix": bad_mix})) == "INVALID_PROFILE"
    assert err(client.post("/api/missions", json={**mission_body, "name": ""})) == "VALIDATION_ERROR"
    assert err(client.post("/api/missions", json={**mission_body, "reserveFraction": 1.0})) == "VALIDATION_ERROR"
    assert err(client.post("/api/missions", json={**mission_body, "priorities": {"safetyWeight": 1}})) == "INVALID_PROFILE"


def test_custom_mix_is_computed_and_stored(client, mission_body):
    mix = [{"presetKey": "BALANCED", "percent": 60}, {"presetKey": "SCIENCE_FOCUSED", "percent": 40}]
    m = create(client, mission_body, profile="CUSTOM", priorityMix=mix, objective="Core the layered rock")
    assert m["priorities"]["safetyWeight"] == pytest.approx(0.23) and m["priorities"]["scienceWeight"] == pytest.approx(0.30)
    assert m["priorityMix"][0] == {"presetKey": "BALANCED", "percent": 60.0} and m["objective"] == "Core the layered rock"
    m2 = client.patch(f"/api/missions/{m['id']}", json={"profile": "SHORTEST"}).get_json()
    assert m2["priorityMix"] == [] and m2["priorities"]["distanceWeight"] == pytest.approx(0.5)


def test_resources_user_value_wins(client, mission_body):
    m = create(client, mission_body, resources={"oxygenKg": 0.7})
    r = client.get(f"/api/missions/{m['id']}/resources").get_json()
    assert r["oxygenKg"]["source"] == "USER_INPUT" and r["oxygenKg"]["value"] == 0.7
    assert r["batteryWh"]["source"] == "DEFAULT_ASSUMPTION" and r["providers"][0]["kind"] == "DEFAULTS"
    assert r["usableOxygenKg"] == pytest.approx(0.56)
    r = client.put(f"/api/missions/{m['id']}/resources", json={"batteryWh": 500, "reserveFraction": 0.3}).get_json()
    assert r["batteryWh"]["value"] == 500 and r["reserveFraction"] == 0.3
    assert err(client.put(f"/api/missions/{m['id']}/resources", json={"oxygenKg": -1})) == "VALIDATION_ERROR"


def test_status_flow_and_finalized(client, mission_body):
    m = create(client, mission_body)
    assert err(client.patch(f"/api/missions/{m['id']}/status", json={"status": "FINALIZED"})) == "INVALID_STATUS_TRANSITION"
    assert client.patch(f"/api/missions/{m['id']}/status", json={"status": "PLANNED"}).status_code == 200
    assert client.patch(f"/api/missions/{m['id']}/status", json={"status": "FINALIZED"}).status_code == 200
    assert err(client.patch(f"/api/missions/{m['id']}", json={"name": "x"})) == "MISSION_FINALIZED"
    assert err(client.post(f"/api/missions/{m['id']}/routes/recalculate")) == "MISSION_FINALIZED"
    d = client.post(f"/api/missions/{m['id']}/duplicate").get_json()
    assert d["status"] == "DRAFT" and d["name"].endswith("(copy)")
    assert [x["id"] for x in client.get("/api/missions").get_json()][0] == d["id"]   # newest first


# ---------------------------------------------------------------- routes
def test_routes_full_contract(client, mission_body):
    m = create(client, mission_body)
    routes = client.post(f"/api/missions/{m['id']}/routes").get_json()
    assert [r["routeType"] for r in routes] == ["SAFEST", "SHORTEST", "SCIENCE_FOCUSED", "MISSION_PRIORITY"]
    for r in routes:
        assert ROUTE_FIELDS <= set(r), ROUTE_FIELDS - set(r)
        assert r["feasible"] and r["geometry"]["type"] == "LineString" and len(r["geometry"]["coordinates"][0]) == 3
        assert r["costProvider"]["kind"] == "ALGORITHM" and r["costModelVersion"] == 0
        assert r["maxSlopeDeg"] <= 20.5 and 0 <= r["assessment"]["dataConfidence"] <= 1
        assert r["returnFeasibility"]["refillPointName"] == "Start (base)"
    by = {r["routeType"]: r for r in routes}
    assert by["MISSION_PRIORITY"]["missionMatch"] == 100.0
    assert all(r["missionMatch"] <= 100.0 for r in routes)
    assert by["SHORTEST"]["distanceM"] <= min(r["distanceM"] for r in routes) + 1e-6
    # select, ownership, report
    other = create(client, mission_body, name="Other")
    assert err(client.put(f"/api/missions/{other['id']}/selected-route", json={"routeId": routes[0]["id"]})) == "ROUTE_NOT_IN_MISSION"
    sel = client.put(f"/api/missions/{m['id']}/selected-route", json={"routeId": routes[0]["id"]}).get_json()
    assert sel["selectedRouteId"] == routes[0]["id"]
    rep = client.get(f"/api/missions/{m['id']}/report").get_json()
    assert rep["recommendedRoute"]["id"] == routes[0]["id"] and rep["notice"].startswith("Prototype")
    assert rep["caveats"] and rep["providersUsed"] and len(rep["terrainClassMapping"]) == 15
    assert err(client.get(f"/api/missions/{other['id']}/report")) == "ROUTES_NOT_CALCULATED"
    again = client.post(f"/api/missions/{m['id']}/routes/recalculate").get_json()
    assert client.get(f"/api/missions/{m['id']}").get_json()["selectedRouteId"] is None and again[0]["id"] != routes[0]["id"]


def test_low_oxygen_is_infeasible(client, mission_body):
    m = create(client, mission_body, resources={"oxygenKg": 0.15})
    routes = client.post(f"/api/missions/{m['id']}/routes").get_json()
    for r in routes:
        assert r["feasible"] is False and r["overallRisk"] == "CRITICAL"
        assert r["returnFeasibility"]["limitingResource"] == "OXYGEN"


def test_no_refill_point(client, mission_body):
    # start is not a base and the only refill point (the base) is far from this trip -> still reachable? use a short trip away from base
    slon, slat = ll(-3000, 1000)
    m = create(client, mission_body, startLon=slon, startLat=slat, startIsBase=False, resources={"oxygenKg": 0.05, "batteryWh": 60})
    for r in client.post(f"/api/missions/{m['id']}/routes").get_json():
        assert r["feasible"] is False


def test_high_hazard_warning_is_avoided(client, mission_body):
    m = create(client, mission_body)
    base = client.post(f"/api/missions/{m['id']}/routes").get_json()[1]           # SHORTEST
    mid_pt = base["geometry"]["coordinates"][len(base["geometry"]["coordinates"]) // 2]
    client.post(f"/api/missions/{m['id']}/annotations", json={"kind": "HAZARD_WARNING", "lon": mid_pt[0], "lat": mid_pt[1],
                                                              "severity": "HIGH", "radiusM": 150, "note": "Loose slope"})
    after = client.post(f"/api/missions/{m['id']}/routes/recalculate").get_json()[1]
    from shapely.geometry import LineString, Point
    from redgrid.geo import LocalMetric
    lm = LocalMetric(mid_pt[0], mid_pt[1])
    xy = [lm.to_xy(c[0], c[1]) for c in after["geometry"]["coordinates"]]
    assert LineString([(float(x), float(y)) for x, y in xy]).distance(Point(0, 0)) >= 140   # stays outside the warning circle


def test_science_stop_is_visited(client, mission_body):
    m = create(client, mission_body)
    slon, slat = ll(-1500, -1200)
    a = client.post(f"/api/missions/{m['id']}/annotations", json={"kind": "SCIENCE_STOP", "lon": slon, "lat": slat, "durationMin": 30,
                                                                  "note": "Sample"}).get_json()
    r = client.post(f"/api/missions/{m['id']}/routes").get_json()[0]
    from redgrid.geo import LocalMetric
    lm = LocalMetric(slon, slat)
    assert min(float((lambda x, y: (x * x + y * y) ** 0.5)(*lm.to_xy(c[0], c[1]))) for c in r["geometry"]["coordinates"]) < 12
    assert client.delete(f"/api/missions/{m['id']}/annotations/{a['id']}").status_code == 204
    assert err(client.delete(f"/api/missions/{m['id']}/annotations/{a['id']}")) == "ANNOTATION_NOT_FOUND"
