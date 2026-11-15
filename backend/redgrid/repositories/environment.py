from __future__ import annotations


class EnvironmentRepository:
    def __init__(self, db):
        self.db = db

    def get_demo_window(self) -> dict | None:
        r = self.db.execute("SELECT * FROM demo_window WHERE id = 1").fetchone()
        return dict(r) if r else None

    def get_snapshot(self, region_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM environmental_snapshot WHERE region_id = ?", (region_id,)).fetchone()
        return dict(r) if r else None

    def set_demo_window(self, w: dict) -> None:
        self.db.execute("DELETE FROM demo_window")
        self.db.execute("""INSERT INTO demo_window (id, start_sol, end_sol, start_utc, end_utc, solar_longitude_start,
                           solar_longitude_end, source, data_state) VALUES (1,?,?,?,?,?,?,?,?)""",
                        (w["startSol"], w["endSol"], w["startUtc"], w["endUtc"], w.get("solarLongitudeStart"),
                         w.get("solarLongitudeEnd"), w["source"], w.get("dataState", "HISTORICAL_OBSERVATION")))

    def replace_observations(self, region_id: int, rows: list[dict]) -> int:
        self.db.execute("DELETE FROM environmental_observation WHERE region_id = ?", (region_id,))
        for o in rows:
            self.db.execute("""INSERT INTO environmental_observation (region_id, sol, measurement_lon, measurement_lat, observed_at,
                               variable, unit, value, source, data_state) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (region_id, o["sol"], o.get("lon"), o.get("lat"), o["observed_at"], o["variable"], o.get("unit"),
                             o["value"], o.get("source"), o.get("data_state", "HISTORICAL_OBSERVATION")))
        return len(rows)
