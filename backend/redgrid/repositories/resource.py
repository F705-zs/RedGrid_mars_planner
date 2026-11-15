from __future__ import annotations

from ..models import ResourceValue


class ResourceRepository:
    """USER_INPUT and SENSOR readings only; defaults come from the defaults provider (never stored)."""

    def __init__(self, db):
        self.db = db

    def get_current(self, mission_id: int) -> dict[str, ResourceValue]:
        rows = self.db.execute("SELECT * FROM resource_current WHERE mission_id = ?", (mission_id,))
        return {r["variable"]: ResourceValue(variable=r["variable"], value=r["value"], unit=r["unit"], source=r["source"],
                                             observed_at=r["observed_at"], data_state=r["data_state"]) for r in rows}

    def add_reading(self, mission_id: int, variable: str, value: float, unit: str, observed_at: str,
                    source: str = "USER_INPUT", data_state: str = "LATEST_OBSERVATION") -> None:
        self.db.execute("""INSERT INTO resource_reading (mission_id, variable, value, unit, observed_at, source, data_state)
                           VALUES (?,?,?,?,?,?,?)""", (mission_id, variable, value, unit, observed_at, source, data_state))

    def copy(self, from_mission: int, to_mission: int) -> None:
        self.db.execute("""INSERT INTO resource_reading (mission_id, variable, value, unit, observed_at, source, data_state)
                           SELECT ?, variable, value, unit, observed_at, source, data_state FROM resource_reading
                           WHERE mission_id = ?""", (to_mission, from_mission))
