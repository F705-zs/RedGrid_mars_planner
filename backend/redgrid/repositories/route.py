from __future__ import annotations

import json

from ..errors import ApiError


class RouteRepository:
    """Stores routes in the API shape (camelCase dict) across route, route_assessment, return_feasibility, route_warning."""

    def __init__(self, db):
        self.db = db

    def replace_all(self, mission_id: int, routes: list[dict]) -> list[dict]:
        self.db.execute("UPDATE mission SET selected_route_id = NULL WHERE id = ?", (mission_id,))
        self.db.execute("DELETE FROM route WHERE mission_id = ?", (mission_id,))
        out = []
        for r in routes:
            cp, pr = r["costProvider"], r["priorityResolver"]
            cur = self.db.execute("""INSERT INTO route (mission_id, route_type, geometry_json, elevation_profile_json, feasible, overall_risk,
                mission_match, distance_m, duration_min, average_slope_deg, max_slope_deg, elevation_gain_m, elevation_loss_m,
                terrain_difficulty, science_score, hazard_count, recommendation, oxygen_used_kg, battery_used_wh, oxygen_left_kg,
                battery_left_wh, cost_model_id, cost_provider, cost_provider_kind, cost_provider_transport, cost_provider_version,
                priority_resolver, priority_resolver_kind, priority_resolver_version, window_json, calculated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mission_id, r["routeType"], json.dumps(r["geometry"]), json.dumps(r["elevationProfile"]), int(r["feasible"]),
                 r["overallRisk"], r["missionMatch"], r["distanceM"], r["durationMin"], r["averageSlopeDeg"], r["maxSlopeDeg"],
                 r["elevationGainM"], r["elevationLossM"], r["terrainDifficulty"], r["scienceScore"], r["hazardCount"],
                 r["recommendation"], r["oxygenUsedKg"], r["batteryUsedWh"], r["oxygenLeftKg"], r["batteryLeftWh"],
                 r["costModelId"], cp["name"], cp["kind"], cp["transport"], cp["version"], pr["name"], pr["kind"], pr["version"],
                 json.dumps(r["window"]), r["calculatedAt"]))
            rid = cur.lastrowid
            a = r["assessment"]
            self.db.execute("INSERT INTO route_assessment VALUES (?,?,?,?)", (rid, a["dustStatus"], a["communicationStatus"], a["dataConfidence"]))
            rf = r["returnFeasibility"]
            if rf is not None:
                self.db.execute("INSERT INTO return_feasibility VALUES (?,?,?,?,?,?,?,?,?)",
                                (rid, int(rf["feasible"]), rf["distanceToSafePointM"], rf["returnDurationMin"], rf["maximumReturnDistanceM"],
                                 rf["safePointName"], rf["reason"], rf["limitingResource"], rf["refillPointName"]))
            for w in r["warnings"]:
                self.db.execute("INSERT INTO route_warning (route_id, message) VALUES (?,?)", (rid, w))
            out.append(self.get_by_id(rid))
        return out

    def _route(self, r) -> dict:
        a = self.db.execute("SELECT * FROM route_assessment WHERE route_id = ?", (r["id"],)).fetchone()
        rf = self.db.execute("SELECT * FROM return_feasibility WHERE route_id = ?", (r["id"],)).fetchone()
        version = None
        if r["cost_model_id"] is not None:
            version = self.db.execute("SELECT version FROM cost_model WHERE id = ?", (r["cost_model_id"],)).fetchone()["version"]
        return {
            "id": r["id"], "missionId": r["mission_id"], "routeType": r["route_type"],
            "geometry": json.loads(r["geometry_json"]), "elevationProfile": json.loads(r["elevation_profile_json"] or "[]"),
            "feasible": bool(r["feasible"]), "overallRisk": r["overall_risk"], "missionMatch": r["mission_match"],
            "distanceM": r["distance_m"], "durationMin": r["duration_min"], "averageSlopeDeg": r["average_slope_deg"],
            "maxSlopeDeg": r["max_slope_deg"], "elevationGainM": r["elevation_gain_m"], "elevationLossM": r["elevation_loss_m"],
            "terrainDifficulty": r["terrain_difficulty"], "hazardCount": r["hazard_count"], "scienceScore": r["science_score"],
            "oxygenUsedKg": r["oxygen_used_kg"], "batteryUsedWh": r["battery_used_wh"], "oxygenLeftKg": r["oxygen_left_kg"],
            "batteryLeftWh": r["battery_left_wh"], "costModelId": r["cost_model_id"], "costModelVersion": version,
            "costProvider": {"name": r["cost_provider"], "kind": r["cost_provider_kind"], "transport": r["cost_provider_transport"],
                             "version": r["cost_provider_version"], "status": "READY"},
            "priorityResolver": {"name": r["priority_resolver"], "kind": r["priority_resolver_kind"], "transport": "LOCAL" if r["priority_resolver_kind"] == "ALGORITHM" else "HTTP",
                                 "version": r["priority_resolver_version"], "status": "READY"},
            "window": json.loads(r["window_json"]) if r["window_json"] else None, "calculatedAt": r["calculated_at"],
            "assessment": {"dustStatus": a["dust_status"], "communicationStatus": a["communication_status"], "dataConfidence": a["data_confidence"]},
            "returnFeasibility": None if rf is None else {
                "feasible": bool(rf["feasible"]), "distanceToSafePointM": rf["distance_to_safe_point_m"],
                "returnDurationMin": rf["return_duration_min"], "maximumReturnDistanceM": rf["maximum_return_distance_m"],
                "safePointName": rf["safe_point_name"], "reason": rf["reason"], "limitingResource": rf["limiting_resource"],
                "refillPointName": rf["refill_point_name"]},
            "warnings": [w["message"] for w in self.db.execute("SELECT message FROM route_warning WHERE route_id = ? ORDER BY id", (r["id"],))],
            "recommendation": r["recommendation"],
        }

    def get_by_mission(self, mission_id: int) -> list[dict]:
        order = "CASE route_type WHEN 'SAFEST' THEN 1 WHEN 'SHORTEST' THEN 2 WHEN 'SCIENCE_FOCUSED' THEN 3 ELSE 4 END"
        return [self._route(r) for r in self.db.execute(f"SELECT * FROM route WHERE mission_id = ? ORDER BY {order}", (mission_id,))]

    def get_by_id(self, route_id: int) -> dict:
        r = self.db.execute("SELECT * FROM route WHERE id = ?", (route_id,)).fetchone()
        if r is None:
            raise ApiError("ROUTE_NOT_FOUND", f"Route {route_id} does not exist")
        return self._route(r)
