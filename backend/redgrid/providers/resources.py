"""Resource providers: sensor (future, HTTP) and defaults (planning constants, local)."""
from __future__ import annotations

from ..models import ResourceValue
from .contracts import ProviderInfo
from .http_base import HttpProviderBase

DEFAULT_KEYS = {"OXYGEN_KG": ("default_oxygen_kg", "kg"), "BATTERY_WH": ("default_battery_wh", "Wh"),
                "METABOLIC_RATE_W": ("metabolic_rate_w", "W"), "SUIT_POWER_W": ("default_suit_power_w", "W")}


class DefaultResourceProvider:
    def __init__(self, constants):
        self.constants = constants

    def info(self) -> ProviderInfo:
        return ProviderInfo("planning-constant-defaults", "DEFAULTS", "LOCAL", "1")

    def is_ready(self) -> bool:
        return True

    def values(self, mission_id: int) -> list[ResourceValue]:
        out = []
        for var, (key, unit) in DEFAULT_KEYS.items():
            c = self.constants.get(key)
            out.append(ResourceValue(variable=var, value=float(c.value), unit=unit, source="DEFAULT_ASSUMPTION",
                                     observed_at=None, data_state=c.data_state))
        return out


class SensorResourceProvider(HttpProviderBase):
    """Future work: suit telemetry. Not ready unless REDGRID_SENSOR_URL points at a live service."""

    def info(self) -> ProviderInfo:
        h = self._health or {}
        return ProviderInfo(h.get("name", "suit-sensor"), "SENSOR", "HTTP", str(h.get("version", "none")),
                            "READY" if self._ready else "UNAVAILABLE")

    def values(self, mission_id: int) -> list[ResourceValue]:
        a = self._get(f"/v1/missions/{mission_id}/resources")
        return [ResourceValue(variable=v["variable"], value=float(v["value"]), unit=v["unit"], source="SENSOR",
                              observed_at=v.get("observedAt"), data_state=v.get("dataState", "LATEST_OBSERVATION"))
                for v in a.get("values", []) if v.get("variable") in DEFAULT_KEYS and float(v["value"]) >= 0]
