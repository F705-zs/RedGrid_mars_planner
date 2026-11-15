import type {
  AnnotationKind,
  DataState,
  FeatureType,
  InputSource,
  LimitingResource,
  MissionStatus,
  PriorityPreset,
  RiskLevel,
  RouteType,
  Severity,
  TerrainClass,
} from "@/types";

export const DATA_STATE_LABEL: Record<DataState, string> = {
  LATEST_OBSERVATION: "Latest observation",
  HISTORICAL_OBSERVATION: "Historical observation",
  MODELLED_CONDITION: "Modelled condition",
  DEMONSTRATION_DATA: "Demonstration data",
  DATA_UNAVAILABLE: "Data unavailable",
  LIMITED_CONFIDENCE: "Limited confidence",
  DERIVED: "Derived",
};

export const DATA_STATE_HINT: Record<DataState, string> = {
  LATEST_OBSERVATION: "Most recent available observation.",
  HISTORICAL_OBSERVATION: "Observed in the past; conditions may have changed.",
  MODELLED_CONDITION: "Produced by a model, not directly observed.",
  DEMONSTRATION_DATA: "Placeholder value for demonstration. Not a real result.",
  DATA_UNAVAILABLE: "No data covers this item.",
  LIMITED_CONFIDENCE: "Sparse or uncertain source data. Verify before use.",
  DERIVED: "Computed from another dataset.",
};

export const STATUS_LABEL: Record<MissionStatus, string> = {
  DRAFT: "Draft",
  PLANNED: "Planned",
  FINALIZED: "Finalized",
};

export const PRESET_LABEL: Record<PriorityPreset, string> = {
  BALANCED: "Balanced",
  SAFETY_FOCUSED: "Safety focused",
  SCIENCE_FOCUSED: "Science focused",
  SHORTEST: "Shortest",
  CUSTOM: "Custom",
};

export const ROUTE_TYPE_LABEL: Record<RouteType, string> = {
  SAFEST: "Safest",
  SHORTEST: "Shortest",
  SCIENCE_FOCUSED: "Science focused",
  MISSION_PRIORITY: "Mission priority",
};

/** Short letter shown next to route colours so colour is never the only cue. */
export const ROUTE_TYPE_CODE: Record<RouteType, string> = {
  SAFEST: "A",
  SHORTEST: "B",
  SCIENCE_FOCUSED: "C",
  MISSION_PRIORITY: "D",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  LOW: "Low risk",
  MODERATE: "Moderate risk",
  HIGH: "High risk",
  CRITICAL: "Critical risk",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
};

export const ANNOTATION_LABEL: Record<AnnotationKind, string> = {
  SCIENCE_STOP: "Science stop",
  HAZARD_WARNING: "Hazard warning",
};

export const FEATURE_TYPE_LABEL: Record<FeatureType, string> = {
  HAZARD: "Hazard",
  RIM_SCARP: "Crater rim or scarp",
  SCIENCE_TARGET: "Science target",
  SAFE_POINT: "Safe point",
  COMMUNICATION_ASSET: "Communication asset",
  ROVER_PATH: "Rover path",
  TERRAIN_UNIT: "Geology unit",
  LANDING_ELLIPSE: "Landing ellipse",
};

export const TERRAIN_CLASS_LABEL: Record<TerrainClass, string> = {
  REGOLITH: "Regolith",
  BEDROCK: "Bedrock",
  SAND: "Sand",
  BOULDER_FIELD: "Boulder field",
};

/** Where an oxygen / battery value came from (the user's value always wins). */
export const INPUT_SOURCE_LABEL: Record<InputSource, string> = {
  USER_INPUT: "Your value",
  SENSOR: "Sensor",
  DEFAULT_ASSUMPTION: "Default (assumption)",
};

export const LIMITING_RESOURCE_LABEL: Record<LimitingResource, string> = {
  OXYGEN: "Oxygen",
  BATTERY: "Battery",
  TIME: "Time",
  NONE: "None",
};

export const PRIORITY_LABEL = {
  safetyWeight: "Safety",
  scienceWeight: "Science",
  distanceWeight: "Distance",
  walkingDifficultyWeight: "Walking difficulty",
  returnWeight: "Return margin",
  environmentWeight: "Environment",
  roverPathWeight: "Follow rover path",
} as const;
