"""MissionService (RedGrid Class Specification): missions, priorities and the custom mix, annotations, resources."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..enums import PRESETS, PRIORITY_FIELDS, RESOURCE_VARIABLES
from ..errors import ApiError, validation
from ..models import Annotation, MixEntry, Mission, PriorityProfile, ResourceSnapshot

RESOURCE_BODY = {"oxygenKg": ("OXYGEN_KG", "kg"), "batteryWh": ("BATTERY_WH", "Wh"),
                 "metabolicRateW": ("METABOLIC_RATE_W", "W"), "suitPowerW": ("SUIT_POWER_W", "W")}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(body: dict, key: str, required: bool = True):
    v = body.get(key)
    if v is None:
        if required:
            raise validation(f"{key} is required", field=key)
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise validation(f"{key} must be a number", field=key)
    return float(v)


class MissionService:
    def __init__(self, *, missions, regions, presets, resources, constants, resource_chain):
        self.missions, self.regions, self.presets = missions, regions, presets
        self.resources, self.k, self.resource_chain = resources, constants, resource_chain

    # ------------------------------------------------------------ priorities
    def resolve_priorities(self, profile: str, body: dict) -> tuple[PriorityProfile, list[MixEntry]]:
        if profile != "CUSTOM":
            if body.get("priorities") is not None or body.get("priorityMix"):
                raise ApiError("INVALID_PROFILE", "priorities and priorityMix are only accepted with profile CUSTOM")
            return self.presets.get_by_key(profile).weights.normalised(), []
        mix = self._mix(body.get("priorityMix") or [])
        if body.get("priorities") is not None:
            if not isinstance(body["priorities"], dict):
                raise ApiError("INVALID_PROFILE", "priorities must be an object")
            p = PriorityProfile.from_dict(body["priorities"])
        elif mix:
            acc = {k: 0.0 for k in PRIORITY_FIELDS}
            for e in mix:
                w = self.presets.get_by_key(e.preset_key).weights.as_dict()
                for k in PRIORITY_FIELDS:
                    acc[k] += e.percent / 100.0 * w[k]
            p = PriorityProfile(**acc)
        else:
            raise ApiError("INVALID_PROFILE", "A CUSTOM mission needs priorities, priorityMix or both")
        if not p.validate():
            raise ApiError("INVALID_PROFILE", "Weights must be zero or more and not all zero")
        return p.normalised(), mix

    @staticmethod
    def _mix(raw) -> list[MixEntry]:
        if not isinstance(raw, list):
            raise ApiError("INVALID_PROFILE", "priorityMix must be a list")
        if not raw:
            return []
        seen, out = set(), []
        for e in raw:
            key, pct = (e or {}).get("presetKey"), (e or {}).get("percent")
            if key not in PRESETS:
                raise ApiError("INVALID_PROFILE", f"Unknown or not allowed preset in mix: {key}")
            if key in seen:
                raise ApiError("INVALID_PROFILE", f"Preset {key} appears twice in the mix")
            if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not (0 < pct <= 100):
                raise ApiError("INVALID_PROFILE", "Mix percents must be above 0 and at most 100")
            seen.add(key)
            out.append(MixEntry(key, float(pct)))
        if abs(sum(e.percent for e in out) - 100.0) > 0.01:
            raise ApiError("INVALID_PROFILE", "Mix percents must sum to 100")
        return out

    # ------------------------------------------------------------ validation helpers
    def _check_point(self, region, lon, lat, field):
        if not region.contains(lon, lat):
            raise ApiError("OUT_OF_REGION", f"The {'start' if field == 'start' else 'destination'} is outside the region", {"field": field})
        if not region.routable_geometry:
            raise ApiError("DATA_NOT_PREPARED", "The routable area has not been prepared yet")
        if not region.is_routable(lon, lat):
            raise ApiError("OUT_OF_COVERAGE", f"The {'start' if field == 'start' else 'destination'} is outside the area with full terrain data",
                           {"field": field})

    @staticmethod
    def _text(body, key, max_len, required):
        v = body.get(key)
        if v is None:
            if required:
                raise validation(f"{key} is required", field=key)
            return None
        if not isinstance(v, str):
            raise validation(f"{key} must be text", field=key)
        v = v.strip()
        if required and not v:
            raise validation(f"{key} must not be empty", field=key)
        if len(v) > max_len:
            raise validation(f"{key} must be at most {max_len} characters", field=key)
        return v or None

    def _reserve(self, body, default):
        if "reserveFraction" not in body or body["reserveFraction"] is None:
            return default
        r = _num(body, "reserveFraction")
        if not (0 <= r < 1):
            raise validation("reserveFraction must be from 0 to below 1", field="reserveFraction")
        return r

    @staticmethod
    def _bool(body, key, default):
        v = body.get(key, default)
        if v is None:
            return default
        if not isinstance(v, bool):
            raise validation(f"{key} must be true or false", field=key)
        return v

    # ------------------------------------------------------------ missions
    def create(self, body: dict) -> Mission:
        if not isinstance(body, dict):
            raise validation("A JSON object is required")
        rid = body.get("regionId")
        if not isinstance(rid, int) or isinstance(rid, bool):
            raise validation("regionId is required", field="regionId")
        region = self.regions.get_by_id(rid)
        name = self._text(body, "name", 80, True)
        objective = self._text(body, "objective", 500, False)
        coords = {k: _num(body, k) for k in ("startLon", "startLat", "destLon", "destLat")}
        profile = body.get("profile")
        if profile not in PRESETS + ["CUSTOM"]:
            raise validation("profile must be one of BALANCED, SAFETY_FOCUSED, SCIENCE_FOCUSED, SHORTEST, CUSTOM", field="profile")
        self._check_point(region, coords["startLon"], coords["startLat"], "start")
        self._check_point(region, coords["destLon"], coords["destLat"], "dest")
        prio, mix = self.resolve_priorities(profile, body)
        m = Mission(id=0, region_id=rid, name=name, objective=objective, start_lon=coords["startLon"], start_lat=coords["startLat"],
                    dest_lon=coords["destLon"], dest_lat=coords["destLat"], profile=profile, priorities=prio, priority_mix=mix,
                    status="DRAFT", selected_route_id=None,
                    reserve_fraction=self._reserve(body, self.k.value("default_reserve_fraction")),
                    start_is_base=self._bool(body, "startIsBase", True), created_at=now_iso())
        values = self._resource_values(body["resources"]) if body.get("resources") is not None else {}
        mid = self.missions.add(m)
        self._store_resources(mid, values)
        return self.missions.get_by_id(mid)

    def get(self, mission_id: int) -> Mission:
        return self.missions.get_by_id(mission_id)

    def list(self, status: str | None) -> list[Mission]:
        if status is not None and status not in ("DRAFT", "PLANNED", "FINALIZED"):
            raise validation("status must be DRAFT, PLANNED or FINALIZED", field="status")
        return self.missions.get_all(status)

    def update(self, mission_id: int, body: dict) -> Mission:
        if not isinstance(body, dict):
            raise validation("A JSON object is required")
        m = self.missions.get_by_id(mission_id)
        m.assert_editable()
        region = self.regions.get_by_id(m.region_id)
        if "name" in body:
            m.name = self._text(body, "name", 80, True)
        if "objective" in body:
            m.objective = self._text(body, "objective", 500, False)
        moved = False
        for key, attr in (("startLon", "start_lon"), ("startLat", "start_lat"), ("destLon", "dest_lon"), ("destLat", "dest_lat")):
            if key in body:
                setattr(m, attr, _num(body, key))
                moved = True
        if moved:
            self._check_point(region, m.start_lon, m.start_lat, "start")
            self._check_point(region, m.dest_lon, m.dest_lat, "dest")
        if any(k in body for k in ("profile", "priorities", "priorityMix")):
            profile = body.get("profile", m.profile)
            if profile not in PRESETS + ["CUSTOM"]:
                raise validation("profile is not valid", field="profile")
            if profile == "CUSTOM" and body.get("priorities") is None and not body.get("priorityMix"):
                body = {**body, "priorities": m.priorities.as_dict(), "priorityMix": [{"presetKey": e.preset_key, "percent": e.percent} for e in m.priority_mix]}
            m.profile = profile
            m.priorities, m.priority_mix = self.resolve_priorities(profile, body)
        m.reserve_fraction = self._reserve(body, m.reserve_fraction)
        m.start_is_base = self._bool(body, "startIsBase", m.start_is_base)
        self.missions.update(m)
        if body.get("resources") is not None:
            self._store_resources(mission_id, self._resource_values(body["resources"]))
        return self.missions.get_by_id(mission_id)

    def duplicate(self, mission_id: int) -> Mission:
        m = self.missions.get_by_id(mission_id)
        m.name = (m.name + " (copy)")[:80]
        m.status, m.selected_route_id, m.created_at = "DRAFT", None, now_iso()
        new_id = self.missions.add(m)
        self.resources.copy(mission_id, new_id)
        for a in self.missions.get_annotations(mission_id):
            a.mission_id = new_id
            self.missions.add_annotation(a)
        return self.missions.get_by_id(new_id)

    def change_status(self, mission_id: int, body: dict) -> Mission:
        status = (body or {}).get("status")
        if status not in ("DRAFT", "PLANNED", "FINALIZED"):
            raise validation("status must be DRAFT, PLANNED or FINALIZED", field="status")
        m = self.missions.get_by_id(mission_id)
        if not m.can_transition_to(status):
            raise ApiError("INVALID_STATUS_TRANSITION", f"Cannot change status from {m.status} to {status}")
        m.status = status
        self.missions.update(m)
        return self.missions.get_by_id(mission_id)

    # ------------------------------------------------------------ annotations
    def list_annotations(self, mission_id: int):
        self.missions.get_by_id(mission_id)
        return self.missions.get_annotations(mission_id)

    def add_annotation(self, mission_id: int, body: dict) -> Annotation:
        m = self.missions.get_by_id(mission_id)
        m.assert_editable()
        region = self.regions.get_by_id(m.region_id)
        kind = (body or {}).get("kind")
        if kind not in ("SCIENCE_STOP", "HAZARD_WARNING"):
            raise validation("kind must be SCIENCE_STOP or HAZARD_WARNING", field="kind")
        lon, lat = _num(body, "lon"), _num(body, "lat")
        if not region.contains(lon, lat):
            raise ApiError("OUT_OF_REGION", "The annotation is outside the region", {"field": "lon"})
        note = self._text(body, "note", 500, False)
        if kind == "SCIENCE_STOP":
            dur = _num(body, "durationMin", required=False)
            if dur is not None and dur <= 0:
                raise validation("durationMin must be above 0", field="durationMin")
            if body.get("severity") is not None or body.get("radiusM") is not None:
                raise validation("A science stop has no severity or radius")
            a = Annotation(0, mission_id, kind, lon, lat, note, dur, None, None)
        else:
            sev = body.get("severity")
            if sev not in ("LOW", "MEDIUM", "HIGH"):
                raise validation("severity must be LOW, MEDIUM or HIGH", field="severity")
            radius = _num(body, "radiusM")
            if radius <= 0:
                raise validation("radiusM must be above 0", field="radiusM")
            a = Annotation(0, mission_id, kind, lon, lat, note, None, sev, radius)
        return self.missions.add_annotation(a)

    def remove_annotation(self, mission_id: int, annotation_id: int) -> None:
        self.missions.get_by_id(mission_id).assert_editable()
        self.missions.delete_annotation(mission_id, annotation_id)

    # ------------------------------------------------------------ resources
    @staticmethod
    def _resource_values(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise validation("resources must be an object")
        out = {}
        for key, (var, unit) in RESOURCE_BODY.items():
            if raw.get(key) is not None:
                v = _num(raw, key)
                if v < 0:
                    raise validation(f"{key} must be zero or more", field=key)
                out[var] = (v, unit)
        return out

    def _store_resources(self, mission_id: int, values: dict) -> None:
        t = now_iso()
        for var, (v, unit) in values.items():
            self.resources.add_reading(mission_id, var, v, unit, t, "USER_INPUT", "DEMONSTRATION_DATA")

    def get_resources(self, mission_id: int) -> ResourceSnapshot:
        m = self.missions.get_by_id(mission_id)
        current = self.resources.get_current(mission_id)          # newest USER_INPUT, else newest stored SENSOR
        providers = []
        missing = [v for v in RESOURCE_VARIABLES if v not in current]
        for p in self.resource_chain.providers:                  # live sensor first, then the defaults (always ready)
            if not missing:
                break
            if not p.is_ready():
                continue
            try:
                vals = {v.variable: v for v in p.values(mission_id)}
            except Exception:
                continue
            filled = [v for v in missing if v in vals]
            for v in filled:
                current[v] = vals[v]
            if filled:
                providers.append(p.info().as_dict())
                missing = [v for v in missing if v not in filled]
        return ResourceSnapshot(mission_id=mission_id, values=current, reserve_fraction=m.reserve_fraction,
                                start_is_base=m.start_is_base, providers=providers)

    def set_resources(self, mission_id: int, body: dict) -> ResourceSnapshot:
        if not isinstance(body, dict):
            raise validation("A JSON object is required")
        m = self.missions.get_by_id(mission_id)
        m.assert_editable()
        values = self._resource_values(body)
        if "reserveFraction" in body or "startIsBase" in body:
            m.reserve_fraction = self._reserve(body, m.reserve_fraction)
            m.start_is_base = self._bool(body, "startIsBase", m.start_is_base)
            self.missions.update(m)
        self._store_resources(mission_id, values)
        return self.get_resources(mission_id)
