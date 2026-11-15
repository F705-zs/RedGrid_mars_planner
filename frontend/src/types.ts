// RedGrid API contract types (RedGrid API Contract). Field names and shapes mirror the REST contract exactly —
// never rename fields or change shapes here without the API changing first.
// Conventions: camelCase, uppercase enum strings, integer ids, null for empty values,
// ISO 8601 dates, metres (...M), minutes (...Min), degrees (...Deg), °C, Pa, m/s.

/* ---------- Enums ---------- */

export type MissionStatus = "DRAFT" | "PLANNED" | "FINALIZED";
export type PriorityPreset =
  "BALANCED" | "SAFETY_FOCUSED" | "SCIENCE_FOCUSED" | "SHORTEST" | "CUSTOM";
export type RouteType = "SAFEST" | "SHORTEST" | "SCIENCE_FOCUSED" | "MISSION_PRIORITY";
export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
export type AnnotationKind = "SCIENCE_STOP" | "HAZARD_WARNING";
export type Severity = "LOW" | "MEDIUM" | "HIGH";
export type DataState =
  | "LATEST_OBSERVATION"
  | "HISTORICAL_OBSERVATION"
  | "MODELLED_CONDITION"
  | "DEMONSTRATION_DATA"
  | "DATA_UNAVAILABLE"
  | "LIMITED_CONFIDENCE"
  | "DERIVED";
export type LayerKind = "VECTOR" | "RASTER";
export type FeatureType =
  | "HAZARD"
  | "RIM_SCARP"
  | "SCIENCE_TARGET"
  | "SAFE_POINT"
  | "COMMUNICATION_ASSET"
  | "ROVER_PATH"
  | "TERRAIN_UNIT"
  | "LANDING_ELLIPSE";
export type CategoryGroup =
  "HAZARD" | "TERRAIN" | "SCIENCE" | "COMMUNICATION" | "UNCERTAINTY" | "ROVER_PATH";
export type TerrainClass = "REGOLITH" | "BEDROCK" | "SAND" | "BOULDER_FIELD";
export type InputSource = "USER_INPUT" | "SENSOR" | "DEFAULT_ASSUMPTION";
export type LimitingResource = "OXYGEN" | "BATTERY" | "TIME" | "NONE";
export type ProviderKind = "ALGORITHM" | "MODEL" | "SENSOR" | "DEFAULTS";
export type ProviderTransport = "LOCAL" | "HTTP";
export type ProviderStatus = "READY" | "UNAVAILABLE" | "DISABLED";
export type WeightBasis = "REFERENCE" | "PHYSICS_IN_BASE" | "PLACEHOLDER" | "LEARNED";

export const MISSION_STATUSES: MissionStatus[] = ["DRAFT", "PLANNED", "FINALIZED"];
export const PRIORITY_PRESETS: PriorityPreset[] = [
  "BALANCED",
  "SAFETY_FOCUSED",
  "SCIENCE_FOCUSED",
  "SHORTEST",
  "CUSTOM",
];
export const ROUTE_TYPES: RouteType[] = [
  "SAFEST",
  "SHORTEST",
  "SCIENCE_FOCUSED",
  "MISSION_PRIORITY",
];

/* ---------- GeoJSON (coordinates are [lon, lat]) ---------- */

export type Position = [lon: number, lat: number] | [lon: number, lat: number, elevationM: number];

export type GeoJSONGeometry =
  | { type: "Point"; coordinates: Position }
  | { type: "LineString"; coordinates: Position[] }
  | { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPoint"; coordinates: Position[] }
  | { type: "MultiLineString"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] };

export interface LineStringGeometry {
  type: "LineString";
  coordinates: Position[];
}

export interface FeatureProperties {
  id: number;
  featureType: FeatureType;
  name: string | null;
  code: string | null;
  /** SCIENCE_TARGET only, else null. */
  scienceValue: number | null;
  /** SAFE_POINT only, else null. */
  providesRefill: boolean | null;
  /** COMMUNICATION_ASSET only, else null. */
  heightM: number | null;
}

export interface Feature {
  type: "Feature";
  geometry: GeoJSONGeometry;
  properties: FeatureProperties;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

/* ---------- Objects ---------- */

export interface Region {
  id: number;
  name: string;
  bboxWest: number;
  bboxSouth: number;
  bboxEast: number;
  bboxNorth: number;
  coordinateSystem: string;
  centerLon: number;
  centerLat: number;
  defaultZoom: number;
  /** RedGrid: where routes can be calculated (full data). null = data not prepared yet. */
  routableArea: Extract<GeoJSONGeometry, { type: "Polygon" | "MultiPolygon" }> | null;
}

export interface LayerDataset {
  id: number;
  name: string;
  provider: string;
}

export interface Layer {
  id: number;
  regionId: number;
  key: string;
  displayName: string;
  kind: LayerKind;
  dataState: DataState;
  defaultOn: boolean;
  dataset: LayerDataset;
}

export interface Dataset {
  id: number;
  name: string;
  provider: string;
  doi: string | null;
  url: string | null;
  licence: string | null;
  coverage: string | null;
  coordinateSystem: string | null;
  format: string | null;
  resolutionM: number | null;
  accessedOn: string | null;
  isTraining: boolean;
}

export interface ProfileRule {
  group: CategoryGroup;
  scale: number | null;
  maxFactor: number;
  maxVsHazard: number | null;
}

export interface RouteProfile {
  key: RouteType;
  displayName: string;
  /** null for MISSION_PRIORITY (comes from the priority resolver). */
  distanceWeight: number | null;
  rules: ProfileRule[];
}

export interface Priorities {
  safetyWeight: number;
  scienceWeight: number;
  distanceWeight: number;
  walkingDifficultyWeight: number;
  returnWeight: number;
  environmentWeight: number;
  roverPathWeight: number;
}

export const PRIORITY_KEYS: (keyof Priorities)[] = [
  "safetyWeight",
  "scienceWeight",
  "distanceWeight",
  "walkingDifficultyWeight",
  "returnWeight",
  "environmentWeight",
  "roverPathWeight",
];

export type MixPreset = Exclude<PriorityPreset, "CUSTOM">;

export interface PriorityMixEntry {
  presetKey: MixPreset;
  percent: number;
}

export interface PriorityPresetWeights {
  key: MixPreset;
  displayName: string;
  description: string;
  basis: string;
  weights: Priorities;
}

export interface Mission {
  id: number;
  regionId: number;
  name: string;
  objective: string | null;
  startLon: number;
  startLat: number;
  destLon: number;
  destLat: number;
  profile: PriorityPreset;
  priorities: Priorities;
  priorityMix: PriorityMixEntry[];
  status: MissionStatus;
  selectedRouteId: number | null;
  reserveFraction: number;
  startIsBase: boolean;
  createdAt: string;
}

export interface Annotation {
  id: number;
  missionId: number;
  kind: AnnotationKind;
  lon: number;
  lat: number;
  note: string | null;
  durationMin: number | null;
  severity: Severity | null;
  radiusM: number | null;
}

export interface ProviderInfo {
  name: string;
  kind: ProviderKind;
  transport: ProviderTransport;
  version: string;
  status: ProviderStatus;
}

export interface RouteAssessment {
  dustStatus: string;
  communicationStatus: string;
  /** 0–1 share of the route away from terrain-class boundaries. */
  dataConfidence: number | null;
}

export interface ReturnFeasibility {
  feasible: boolean;
  distanceToSafePointM: number | null;
  returnDurationMin: number | null;
  maximumReturnDistanceM: number | null;
  safePointName: string | null;
  reason: string | null;
  limitingResource: LimitingResource;
  refillPointName: string | null;
}

export interface ElevationProfilePoint {
  distanceM: number;
  elevationM: number;
}

export interface Route {
  id: number;
  missionId: number;
  routeType: RouteType;
  geometry: LineStringGeometry;
  elevationProfile: ElevationProfilePoint[];
  feasible: boolean;
  overallRisk: RiskLevel;
  missionMatch: number;
  distanceM: number | null;
  durationMin: number | null;
  averageSlopeDeg: number | null;
  maxSlopeDeg: number | null;
  elevationGainM: number | null;
  elevationLossM: number | null;
  /** Length-weighted energy multiplier relative to flat regolith (1.0 = flat regolith). */
  terrainDifficulty: number | null;
  hazardCount: number | null;
  /** 0–1 share of the corridor's science value passed. */
  scienceScore: number | null;
  oxygenUsedKg: number | null;
  batteryUsedWh: number | null;
  oxygenLeftKg: number | null;
  batteryLeftWh: number | null;
  costModelId: number | null;
  costModelVersion: number | null;
  costProvider: ProviderInfo;
  priorityResolver: ProviderInfo;
  window: { west: number; south: number; east: number; north: number } | null;
  calculatedAt: string;
  assessment: RouteAssessment;
  returnFeasibility: ReturnFeasibility | null;
  warnings: string[];
  recommendation: string;
}

export interface NearFeature {
  id: number;
  featureType: FeatureType;
  name: string | null;
  code: string | null;
  providesRefill: boolean | null;
  geometry: GeoJSONGeometry;
}

export interface DemoWindow {
  startSol: number;
  endSol: number;
  startUtc: string;
  endUtc: string;
  solarLongitudeStart: number | null;
  solarLongitudeEnd: number | null;
  source: string;
  dataState: DataState;
}

export interface EnvironmentalSnapshot {
  regionId: number;
  temperature: number | null;
  pressure: number | null;
  windSpeed: number | null;
  dustStatus: string | null;
  /** RedGrid: number of sols in the demo window that have data. */
  solsWithData: number;
  window: { startSol: number; endSol: number } | null;
  observedAt: string | null;
  dataState: DataState;
  source: string | null;
}

export interface CategoryRef {
  key: string;
  displayName: string;
  group: CategoryGroup;
}

export interface Category extends CategoryRef {
  scope: "SHARED" | "HUMAN_ONLY" | "FIXED";
  layerKey: string;
  rule: string;
  isReference: boolean;
  bit: number;
}

export interface LocationInfo {
  lon: number;
  lat: number;
  /** RedGrid: inside the area where routes can be calculated. */
  routable: boolean;
  elevationM: number | null;
  slopeDeg: number | null;
  roughnessM: number | null;
  terrainUnit: string | null;
  terrainClass: TerrainClass | null;
  terrainClassDataState: DataState;
  categories: CategoryRef[];
  nearestHazard: NearFeature | null;
  nearestScienceTarget: NearFeature | null;
  nearestSafePoint: NearFeature | null;
  nearestRefillPoint: NearFeature | null;
  distanceToNearestHazardM: number | null;
  distanceToNearestScienceTargetM: number | null;
  distanceToNearestSafePointM: number | null;
  distanceToNearestRefillPointM: number | null;
  environment: EnvironmentalSnapshot;
  dataState: DataState;
  dataQuality: string | null;
}

export interface TerrainClassMapping {
  unitSymbol: string;
  unitName: string;
  terrainClass: TerrainClass;
  dataset: LayerDataset;
  reason: string;
}

export interface CategoryWeight {
  categoryKey: string;
  coefficient: number | null;
  weight: number;
  probability: number | null;
  stdError: number | null;
  basis: WeightBasis;
}

export interface CostModel {
  id: number;
  version: number;
  method: "HAND_SET" | "CONDITIONAL_LOGIT";
  status: "DRAFT" | "ACTIVE" | "RETIRED";
  trainedOn: string | null;
  trainingSummary: string | null;
  testScore: number | null;
  createdAt: string;
  weights?: CategoryWeight[];
  trainingSources?: LayerDataset[];
}

export interface PlanningConstant {
  key: string;
  value: number;
  unit: string;
  description: string;
  source: string;
  dataState: DataState;
}

export interface ResourceValue {
  value: number;
  unit: string;
  source: InputSource;
  observedAt: string | null;
  dataState: DataState;
}

export interface Resources {
  missionId: number;
  oxygenKg: ResourceValue;
  batteryWh: ResourceValue;
  metabolicRateW: ResourceValue;
  suitPowerW: ResourceValue;
  reserveFraction: number;
  startIsBase: boolean;
  usableOxygenKg: number;
  usableBatteryWh: number;
  providers: ProviderInfo[];
}

export interface Providers {
  cost: ProviderInfo[];
  priority: ProviderInfo[];
  resource: ProviderInfo[];
}

export interface TerrainGrid {
  regionId: number;
  bbox: { west: number; south: number; east: number; north: number };
  width: number;
  height: number;
  cellSizeM: number;
  minElevationM: number | null;
  maxElevationM: number | null;
  elevations: (number | null)[];
  dataState: DataState;
  dataset: LayerDataset;
}

export interface Report {
  mission: Mission;
  routes: Route[];
  /** Selected route if any, else the best feasible match; null when no route is feasible. */
  recommendedRoute: Route | null;
  annotations: Annotation[];
  sources: Dataset[];
  costModel: CostModel;
  trainingSources: Dataset[];
  providersUsed: ProviderInfo[];
  constants: PlanningConstant[];
  terrainClassMapping: TerrainClassMapping[];
  demoWindow: DemoWindow | null;
  resources: Resources;
  caveats: string[];
  notice: string;
}

/* ---------- Request bodies ---------- */

export interface ResourcesInput {
  oxygenKg?: number;
  batteryWh?: number;
  metabolicRateW?: number;
  suitPowerW?: number;
}

export interface CreateMissionBody {
  regionId: number;
  name: string;
  objective?: string | null;
  startLon: number;
  startLat: number;
  destLon: number;
  destLat: number;
  profile: PriorityPreset;
  /** CUSTOM only: the final seven weights. */
  priorities?: Priorities;
  /** CUSTOM only: how the weights were mixed from presets (percents sum to 100). */
  priorityMix?: PriorityMixEntry[];
  reserveFraction?: number;
  startIsBase?: boolean;
  /** Omitted values come from the backend's default provider (DEFAULT_ASSUMPTION). */
  resources?: ResourcesInput;
}

export type PatchMissionBody = Partial<CreateMissionBody>;

export interface SetResourcesBody extends ResourcesInput {
  reserveFraction?: number;
  startIsBase?: boolean;
}

export interface CreateAnnotationBody {
  kind: AnnotationKind;
  lon: number;
  lat: number;
  note: string;
  durationMin?: number;
  severity?: Severity;
  radiusM?: number;
}

/* ---------- Errors ---------- */

export type ApiErrorCode =
  | "VALIDATION_ERROR"
  | "OUT_OF_REGION"
  | "OUT_OF_COVERAGE"
  | "INVALID_PROFILE"
  | "LAYER_NOT_VECTOR"
  | "LAYER_NOT_RASTER"
  | "REGION_NOT_FOUND"
  | "LAYER_NOT_FOUND"
  | "MISSION_NOT_FOUND"
  | "ROUTE_NOT_FOUND"
  | "ANNOTATION_NOT_FOUND"
  | "COST_MODEL_NOT_FOUND"
  | "INVALID_STATUS_TRANSITION"
  | "MISSION_FINALIZED"
  | "ROUTE_NOT_IN_MISSION"
  | "ROUTES_NOT_CALCULATED"
  | "ROUTE_TOO_LONG"
  | "DATA_NOT_PREPARED"
  | "INTERNAL_ERROR"
  | "NETWORK_ERROR";

export interface ApiErrorBody {
  error: { code: ApiErrorCode | string; message: string; details: Record<string, unknown> };
}
