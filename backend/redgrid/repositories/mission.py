from __future__ import annotations

from ..errors import ApiError
from ..models import Annotation, MixEntry, Mission, PriorityProfile


class MissionRepository:
    def __init__(self, db):
        self.db = db

    def _mission(self, r) -> Mission:
        p = self.db.execute("SELECT * FROM mission_priority_profile WHERE mission_id = ?", (r["id"],)).fetchone()
        prio = PriorityProfile(safetyWeight=p["safety_weight"], scienceWeight=p["science_weight"], distanceWeight=p["distance_weight"],
                               walkingDifficultyWeight=p["walking_difficulty_weight"], returnWeight=p["return_weight"],
                               environmentWeight=p["environment_weight"], roverPathWeight=p["rover_path_weight"])
        return Mission(id=r["id"], region_id=r["region_id"], name=r["name"], objective=r["objective"], start_lon=r["start_lon"],
                       start_lat=r["start_lat"], dest_lon=r["dest_lon"], dest_lat=r["dest_lat"], profile=r["profile"],
                       priorities=prio, priority_mix=self.get_mix(r["id"]), status=r["status"],
                       selected_route_id=r["selected_route_id"], reserve_fraction=r["reserve_fraction"],
                       start_is_base=bool(r["start_is_base"]), created_at=r["created_at"])

    def get_all(self, status: str | None = None) -> list[Mission]:
        q, a = "SELECT * FROM mission", ()
        if status:
            q, a = q + " WHERE status = ?", (status,)
        return [self._mission(r) for r in self.db.execute(q + " ORDER BY created_at DESC, id DESC", a)]

    def get_by_id(self, mission_id: int) -> Mission:
        r = self.db.execute("SELECT * FROM mission WHERE id = ?", (mission_id,)).fetchone()
        if r is None:
            raise ApiError("MISSION_NOT_FOUND", f"Mission {mission_id} does not exist")
        return self._mission(r)

    def add(self, m: Mission) -> int:
        cur = self.db.execute("""INSERT INTO mission (region_id, name, objective, start_lon, start_lat, dest_lon, dest_lat, profile,
                                 status, reserve_fraction, start_is_base, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (m.region_id, m.name, m.objective, m.start_lon, m.start_lat, m.dest_lon, m.dest_lat, m.profile,
                               m.status, m.reserve_fraction, int(m.start_is_base), m.created_at))
        mid = cur.lastrowid
        self.save_priorities(mid, m.priorities)
        self.save_mix(mid, m.priority_mix)
        return mid

    def update(self, m: Mission) -> None:
        self.db.execute("""UPDATE mission SET name=?, objective=?, start_lon=?, start_lat=?, dest_lon=?, dest_lat=?, profile=?,
                           status=?, reserve_fraction=?, start_is_base=? WHERE id=?""",
                        (m.name, m.objective, m.start_lon, m.start_lat, m.dest_lon, m.dest_lat, m.profile, m.status,
                         m.reserve_fraction, int(m.start_is_base), m.id))
        self.save_priorities(m.id, m.priorities)
        self.save_mix(m.id, m.priority_mix)

    def save_priorities(self, mission_id: int, p: PriorityProfile) -> None:
        self.db.execute("""INSERT OR REPLACE INTO mission_priority_profile (mission_id, safety_weight, science_weight, distance_weight,
                           walking_difficulty_weight, return_weight, environment_weight, rover_path_weight) VALUES (?,?,?,?,?,?,?,?)""",
                        (mission_id, p.safetyWeight, p.scienceWeight, p.distanceWeight, p.walkingDifficultyWeight,
                         p.returnWeight, p.environmentWeight, p.roverPathWeight))

    def get_mix(self, mission_id: int) -> list[MixEntry]:
        return [MixEntry(r["preset_key"], r["percent"]) for r in
                self.db.execute("SELECT * FROM mission_priority_mix WHERE mission_id = ? ORDER BY percent DESC, preset_key", (mission_id,))]

    def save_mix(self, mission_id: int, mix: list[MixEntry]) -> None:
        self.db.execute("DELETE FROM mission_priority_mix WHERE mission_id = ?", (mission_id,))
        for e in mix:
            self.db.execute("INSERT INTO mission_priority_mix (mission_id, preset_key, percent) VALUES (?,?,?)",
                            (mission_id, e.preset_key, e.percent))

    def save_selected_route(self, mission_id: int, route_id: int | None) -> None:
        self.db.execute("UPDATE mission SET selected_route_id = ? WHERE id = ?", (route_id, mission_id))

    # --- annotations ---
    @staticmethod
    def _ann(r) -> Annotation:
        return Annotation(id=r["id"], mission_id=r["mission_id"], kind=r["kind"], lon=r["lon"], lat=r["lat"], note=r["note"],
                          duration_min=r["duration_min"], severity=r["severity"], radius_m=r["radius_m"])

    def get_annotations(self, mission_id: int) -> list[Annotation]:
        return [self._ann(r) for r in self.db.execute("SELECT * FROM annotation WHERE mission_id = ? ORDER BY id", (mission_id,))]

    def add_annotation(self, a: Annotation) -> Annotation:
        cur = self.db.execute("""INSERT INTO annotation (mission_id, kind, lon, lat, duration_min, radius_m, note, severity)
                                 VALUES (?,?,?,?,?,?,?,?)""", (a.mission_id, a.kind, a.lon, a.lat, a.duration_min, a.radius_m, a.note, a.severity))
        return self._ann(self.db.execute("SELECT * FROM annotation WHERE id = ?", (cur.lastrowid,)).fetchone())

    def delete_annotation(self, mission_id: int, annotation_id: int) -> None:
        if self.db.execute("DELETE FROM annotation WHERE id = ? AND mission_id = ?", (annotation_id, mission_id)).rowcount == 0:
            raise ApiError("ANNOTATION_NOT_FOUND", f"Annotation {annotation_id} does not exist for mission {mission_id}")
