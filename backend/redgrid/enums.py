"""Enumerations (RedGrid Class Specification). Values are the uppercase names stored in the database."""
from enum import Enum


class _E(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


MissionStatus = _E("MissionStatus", "DRAFT PLANNED FINALIZED")
PriorityPreset = _E("PriorityPreset", "BALANCED SAFETY_FOCUSED SCIENCE_FOCUSED SHORTEST CUSTOM")
RouteType = _E("RouteType", "SAFEST SHORTEST SCIENCE_FOCUSED MISSION_PRIORITY")
RiskLevel = _E("RiskLevel", "LOW MODERATE HIGH CRITICAL")
AnnotationKind = _E("AnnotationKind", "SCIENCE_STOP HAZARD_WARNING")
Severity = _E("Severity", "LOW MEDIUM HIGH")
DataState = _E("DataState", "LATEST_OBSERVATION HISTORICAL_OBSERVATION MODELLED_CONDITION DEMONSTRATION_DATA "
                            "DATA_UNAVAILABLE LIMITED_CONFIDENCE DERIVED")
LimitingResource = _E("LimitingResource", "OXYGEN BATTERY TIME NONE")
TerrainClass = _E("TerrainClass", "REGOLITH BEDROCK SAND BOULDER_FIELD")
ProviderKind = _E("ProviderKind", "ALGORITHM MODEL SENSOR DEFAULTS")
ProviderTransport = _E("ProviderTransport", "LOCAL HTTP")
ProviderStatus = _E("ProviderStatus", "READY UNAVAILABLE DISABLED")

ROUTE_TYPES = ["SAFEST", "SHORTEST", "SCIENCE_FOCUSED", "MISSION_PRIORITY"]
PRESETS = ["BALANCED", "SAFETY_FOCUSED", "SCIENCE_FOCUSED", "SHORTEST"]
# Fixed group order used in CostFactors.logFactors (RedGrid API Contract, Appendix A)
GROUPS = ["HAZARD", "TERRAIN", "SCIENCE", "COMMUNICATION", "UNCERTAINTY", "ROVER_PATH"]
RESOURCE_VARIABLES = {"OXYGEN_KG": ("oxygenKg", "kg"), "BATTERY_WH": ("batteryWh", "Wh"),
                      "METABOLIC_RATE_W": ("metabolicRateW", "W"), "SUIT_POWER_W": ("suitPowerW", "W")}
PRIORITY_FIELDS = ["safetyWeight", "scienceWeight", "distanceWeight", "walkingDifficultyWeight",
                   "returnWeight", "environmentWeight", "roverPathWeight"]
# terrain_class.tif codes (Database Design RedGrid, prepared-data contract)
TERRAIN_CODES = {1: "REGOLITH", 2: "BEDROCK", 3: "SAND", 4: "BOULDER_FIELD"}
STATUS_TRANSITIONS = {("DRAFT", "PLANNED"), ("PLANNED", "FINALIZED"), ("PLANNED", "DRAFT")}
