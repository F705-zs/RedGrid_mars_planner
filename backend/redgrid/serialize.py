"""Model -> RedGrid API Contract JSON (camelCase, null for empty values)."""
from __future__ import annotations

from .models import Annotation, CostModel, Dataset, Feature, Layer, Mission, PresetWeights, Region


def dataset_ref(d: Dataset) -> dict:
    return {"id": d.id, "name": d.name, "provider": d.provider}


def dataset(d: Dataset) -> dict:
    return {"id": d.id, "name": d.name, "provider": d.provider, "doi": d.doi, "url": d.url, "licence": d.licence,
            "coverage": d.coverage, "coordinateSystem": d.coordinate_system, "format": d.format, "resolutionM": d.resolution_m,
            "accessedOn": d.accessed_on, "isTraining": d.is_training}


def region(r: Region) -> dict:
    return {"id": r.id, "name": r.name, "bboxWest": r.bbox.west, "bboxSouth": r.bbox.south, "bboxEast": r.bbox.east,
            "bboxNorth": r.bbox.north, "coordinateSystem": r.coordinate_system, "centerLon": r.center_lon, "centerLat": r.center_lat,
            "defaultZoom": r.default_zoom, "routableArea": r.routable_geometry}


def layer(l: Layer) -> dict:
    return {"id": l.id, "regionId": l.region_id, "key": l.key, "displayName": l.display_name, "kind": l.kind,
            "dataState": l.data_state, "defaultOn": l.default_on, "dataset": dataset_ref(l.dataset)}


def feature_ref(f: Feature | None) -> dict | None:
    if f is None:
        return None
    return {"id": f.id, "featureType": f.feature_type, "name": f.name, "code": f.code,
            "providesRefill": f.provides_refill if f.feature_type == "SAFE_POINT" else None, "geometry": f.geometry}


def feature_geojson(f: Feature) -> dict:
    return {"type": "Feature", "geometry": f.geometry,
            "properties": {"id": f.id, "featureType": f.feature_type, "name": f.name, "code": f.code,
                           "scienceValue": f.science_value if f.feature_type == "SCIENCE_TARGET" else None,
                           "providesRefill": f.provides_refill if f.feature_type == "SAFE_POINT" else None,
                           "heightM": f.height_m if f.feature_type == "COMMUNICATION_ASSET" else None}}


def mission(m: Mission) -> dict:
    return {"id": m.id, "regionId": m.region_id, "name": m.name, "objective": m.objective, "startLon": m.start_lon,
            "startLat": m.start_lat, "destLon": m.dest_lon, "destLat": m.dest_lat, "profile": m.profile,
            "priorities": m.priorities.as_dict(), "priorityMix": [{"presetKey": e.preset_key, "percent": e.percent} for e in m.priority_mix],
            "status": m.status, "selectedRouteId": m.selected_route_id, "reserveFraction": m.reserve_fraction,
            "startIsBase": m.start_is_base, "createdAt": m.created_at}


def annotation(a: Annotation) -> dict:
    return {"id": a.id, "missionId": a.mission_id, "kind": a.kind, "lon": a.lon, "lat": a.lat, "note": a.note,
            "durationMin": a.duration_min, "severity": a.severity, "radiusM": a.radius_m}


def preset(p: PresetWeights) -> dict:
    return {"key": p.key, "displayName": p.display_name, "description": p.description, "basis": p.basis, "weights": p.weights.as_dict()}


def category(c) -> dict:
    return {"key": c.key, "displayName": c.display_name, "group": c.group, "scope": c.scope, "layerKey": c.layer_key,
            "rule": c.rule, "isReference": c.is_reference, "bit": c.bit}


def category_ref(c) -> dict:
    return {"key": c.key, "displayName": c.display_name, "group": c.group}


def cost_model(m: CostModel, training_sources=None, with_weights: bool = True) -> dict:
    d = {"id": m.id, "version": m.version, "method": m.method, "status": m.status, "trainedOn": m.trained_on,
         "trainingSummary": m.training_summary, "testScore": m.test_score, "createdAt": m.created_at}
    if with_weights:
        d["weights"] = [{"categoryKey": w.category_key, "coefficient": w.coefficient, "weight": w.weight, "probability": w.probability,
                         "stdError": w.std_error, "basis": w.basis} for w in (m.weights or [])]
        d["trainingSources"] = [dataset_ref(x) for x in (training_sources or [])]
    return d


def constant(c) -> dict:
    return {"key": c.key, "value": c.value, "unit": c.unit, "description": c.description, "source": c.source, "dataState": c.data_state}


def route_profile(p) -> dict:
    return {"key": p.key, "displayName": p.display_name, "distanceWeight": p.distance_weight,
            "rules": [{"group": r.group, "scale": r.scale, "maxFactor": r.max_factor, "maxVsHazard": r.max_vs_hazard} for r in
                      sorted(p.rules, key=lambda r: ["HAZARD", "TERRAIN", "SCIENCE", "COMMUNICATION", "UNCERTAINTY", "ROVER_PATH"].index(r.group))]}


def demo_window(w: dict | None) -> dict | None:
    if not w:
        return None
    return {"startSol": w["start_sol"], "endSol": w["end_sol"], "startUtc": w["start_utc"], "endUtc": w["end_utc"],
            "solarLongitudeStart": w["solar_longitude_start"], "solarLongitudeEnd": w["solar_longitude_end"],
            "source": w["source"], "dataState": w["data_state"]}


def terrain_mapping(r: dict, ds: Dataset) -> dict:
    return {"unitSymbol": r["unit_symbol"], "unitName": r["unit_name"], "terrainClass": r["terrain_class"],
            "dataset": dataset_ref(ds), "reason": r["reason"]}


def resources(snap) -> dict:
    from .enums import RESOURCE_VARIABLES
    d = {"missionId": snap.mission_id}
    for var, (field, _) in RESOURCE_VARIABLES.items():
        v = snap.values[var]
        d[field] = {"value": v.value, "unit": v.unit, "source": v.source, "observedAt": v.observed_at, "dataState": v.data_state}
    d.update({"reserveFraction": snap.reserve_fraction, "startIsBase": snap.start_is_base,
              "usableOxygenKg": round(snap.usable_oxygen_kg(), 4), "usableBatteryWh": round(snap.usable_battery_wh(), 1),
              "providers": snap.providers})
    return d
