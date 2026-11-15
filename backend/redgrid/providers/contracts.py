from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from ..enums import GROUPS
from ..geo import BBox


@dataclass
class ProviderInfo:
    name: str
    kind: str          # ALGORITHM | MODEL | SENSOR | DEFAULTS
    transport: str     # LOCAL | HTTP
    version: str
    status: str = "READY"

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "transport": self.transport, "version": self.version, "status": self.status}


@dataclass
class CostRequest:
    request_id: str
    region_id: int
    window: BBox
    cell_size_m: float
    width: int
    height: int
    category_catalog_version: str
    category_keys: list[str]
    category_bits: np.ndarray      # uint32 (height, width)
    routable: np.ndarray           # bool (height, width)


@dataclass
class CostFactors:
    provider: ProviderInfo
    log_factors: np.ndarray        # float (6, height, width), group order = GROUPS
    hazard_floor: float
    cost_model_id: int | None = None
    groups: list[str] = field(default_factory=lambda: list(GROUPS))


@dataclass
class PriorityRequest:
    profile: str
    priorities: dict               # normalised seven weights
    mix: list[dict]


@dataclass
class GroupScales:
    provider: ProviderInfo
    hazard: float
    terrain: float
    science: float
    communication: float
    uncertainty: float
    rover_path: float
    distance_weight: float

    def by_group(self) -> dict[str, float]:
        return {"HAZARD": self.hazard, "TERRAIN": self.terrain, "SCIENCE": self.science, "COMMUNICATION": self.communication,
                "UNCERTAINTY": self.uncertainty, "ROVER_PATH": self.rover_path}


@dataclass
class ProviderResult:
    value: object
    answered_by: ProviderInfo
    skipped: list[str]


def catalog_version(categories) -> str:
    """sha256 over (key, rule, bit) of every category, in bit order (RedGrid API Contract, Appendix A)."""
    h = hashlib.sha256()
    for c in sorted(categories, key=lambda c: c.bit):
        h.update(f"{c.key}|{c.rule}|{c.bit}\n".encode())
    return "sha256:" + h.hexdigest()[:16]


class ProviderError(Exception):
    pass


def validate_cost_factors(f: CostFactors, req: CostRequest) -> None:
    if list(f.groups) != list(GROUPS):
        raise ProviderError(f"groups must be {GROUPS}")
    if f.log_factors.shape != (len(GROUPS), req.height, req.width):
        raise ProviderError(f"logFactors shape {f.log_factors.shape} does not match the request")
    if not np.all(np.isfinite(f.log_factors[:, req.routable])):
        raise ProviderError("logFactors contain non-finite values")
    if not (np.isfinite(f.hazard_floor) and f.hazard_floor > 0):
        raise ProviderError("hazardFloor must be a finite number above 0")


def validate_group_scales(s: GroupScales) -> None:
    vals = [s.hazard, s.terrain, s.science, s.communication, s.uncertainty, s.rover_path]
    if not all(np.isfinite(v) and v >= 0 for v in vals):
        raise ProviderError("every exponent must be finite and at least 0")
    if s.uncertainty < 1:
        raise ProviderError("the uncertainty exponent must be at least 1")
    if not (0 <= s.distance_weight <= 1):
        raise ProviderError("distanceWeight must be between 0 and 1")
