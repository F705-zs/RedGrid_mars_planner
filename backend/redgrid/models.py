"""Domain models (RedGrid Class Specification). Plain data; behaviour limited to the rules the spec puts on them."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Point, shape
from shapely.prepared import prep

from .enums import PRIORITY_FIELDS, STATUS_TRANSITIONS
from .errors import ApiError
from .geo import BBox


@dataclass
class Region:
    id: int
    name: str
    bbox: BBox
    coordinate_system: str
    center_lon: float
    center_lat: float
    default_zoom: int
    routable_geometry: dict | None
    _prepared: Any = field(default=None, repr=False, compare=False)

    def contains(self, lon: float, lat: float) -> bool:
        return self.bbox.contains(lon, lat)

    def routable_shape(self):
        return shape(self.routable_geometry) if self.routable_geometry else None

    def is_routable(self, lon: float, lat: float) -> bool:
        if not self.routable_geometry:
            return False
        if self._prepared is None:
            self._prepared = prep(self.routable_shape())
        return self._prepared.covers(Point(lon, lat))


@dataclass
class Dataset:
    id: int
    name: str
    provider: str
    doi: str | None = None
    url: str | None = None
    licence: str | None = None
    coverage: str | None = None
    coordinate_system: str | None = None
    format: str | None = None
    resolution_m: float | None = None
    accessed_on: str | None = None
    is_training: bool = False


@dataclass
class Layer:
    id: int
    region_id: int
    dataset: Dataset
    key: str
    display_name: str
    kind: str
    data_state: str
    default_on: bool
    raster_path: str | None


@dataclass
class Feature:
    id: int
    layer_id: int
    feature_type: str
    name: str | None
    code: str | None
    geometry: dict
    science_value: float | None
    provides_refill: bool
    height_m: float | None


@dataclass
class PlanningConstant:
    key: str
    value: float
    unit: str
    description: str
    source: str
    data_state: str


@dataclass
class Category:
    key: str
    display_name: str
    group: str
    scope: str
    layer_key: str
    rule: str
    is_reference: bool
    bit: int


@dataclass
class CategoryWeight:
    category_key: str
    coefficient: float | None
    weight: float
    probability: float | None
    std_error: float | None
    basis: str


@dataclass
class CostModel:
    id: int
    version: int
    method: str
    status: str
    trained_on: str | None
    training_summary: str | None
    test_score: float | None
    created_at: str
    weights: list[CategoryWeight] | None = None


@dataclass
class ProfileRule:
    route_type: str
    group: str
    scale: float | None
    max_factor: float
    max_vs_hazard: float | None


@dataclass
class RouteProfile:
    key: str
    display_name: str
    distance_weight: float | None
    rules: list[ProfileRule]

    def rule(self, group: str) -> ProfileRule:
        return next(r for r in self.rules if r.group == group)

    def validate(self) -> bool:
        from .enums import GROUPS
        if self.key != "MISSION_PRIORITY" and not (self.distance_weight is not None and 0 <= self.distance_weight <= 1):
            return False
        if sorted(r.group for r in self.rules) != sorted(GROUPS):
            return False
        u = self.rule("UNCERTAINTY").scale
        return u is None or u >= 1


@dataclass
class PriorityProfile:
    """MissionPriorityProfile: seven weights."""
    safetyWeight: float
    scienceWeight: float
    distanceWeight: float
    walkingDifficultyWeight: float
    returnWeight: float
    environmentWeight: float
    roverPathWeight: float

    @classmethod
    def from_dict(cls, d: dict) -> "PriorityProfile":
        missing = [k for k in PRIORITY_FIELDS if k not in d]
        if missing:
            raise ApiError("INVALID_PROFILE", "Every priority weight is required", {"missing": missing})
        try:
            return cls(**{k: float(d[k]) for k in PRIORITY_FIELDS})
        except (TypeError, ValueError):
            raise ApiError("INVALID_PROFILE", "Priority weights must be numbers")

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in PRIORITY_FIELDS}

    def validate(self) -> bool:
        vals = list(self.as_dict().values())
        return all(v >= 0 for v in vals) and sum(vals) > 0

    def normalised(self) -> "PriorityProfile":
        total = sum(self.as_dict().values())
        return PriorityProfile(**{k: round(v / total, 6) for k, v in self.as_dict().items()})


@dataclass
class PresetWeights:
    key: str
    display_name: str
    description: str
    weights: PriorityProfile
    basis: str


@dataclass
class MixEntry:
    preset_key: str
    percent: float


@dataclass
class Mission:
    id: int
    region_id: int
    name: str
    objective: str | None
    start_lon: float
    start_lat: float
    dest_lon: float
    dest_lat: float
    profile: str
    priorities: PriorityProfile
    priority_mix: list[MixEntry]
    status: str
    selected_route_id: int | None
    reserve_fraction: float
    start_is_base: bool
    created_at: str

    def can_transition_to(self, status: str) -> bool:
        return (self.status, status) in STATUS_TRANSITIONS

    def is_editable(self) -> bool:
        return self.status != "FINALIZED"

    def assert_editable(self) -> None:
        if not self.is_editable():
            raise ApiError("MISSION_FINALIZED", f"Mission {self.id} is finalized and cannot be changed")

    def assert_owns_route(self, route_mission_id: int, route_id: int) -> None:
        if route_mission_id != self.id:
            raise ApiError("ROUTE_NOT_IN_MISSION", f"Route {route_id} belongs to another mission")


@dataclass
class Annotation:
    id: int
    mission_id: int
    kind: str
    lon: float
    lat: float
    note: str | None
    duration_min: float | None
    severity: str | None
    radius_m: float | None


@dataclass
class ResourceValue:
    variable: str
    value: float
    unit: str
    source: str
    observed_at: str | None
    data_state: str


@dataclass
class ResourceSnapshot:
    mission_id: int
    values: dict[str, ResourceValue]      # by variable name OXYGEN_KG ...
    reserve_fraction: float
    start_is_base: bool
    providers: list[dict]

    def value(self, var: str) -> float:
        return self.values[var].value

    def usable_oxygen_kg(self) -> float:
        return self.value("OXYGEN_KG") * (1 - self.reserve_fraction)

    def usable_battery_wh(self) -> float:
        return self.value("BATTERY_WH") * (1 - self.reserve_fraction)


def loads(text: str | None):
    return json.loads(text) if text else None
