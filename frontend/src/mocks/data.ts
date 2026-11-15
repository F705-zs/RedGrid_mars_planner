// Offline test fixtures shaped like RedGrid API Contract. Placeholders, not real results; used only when
// VITE_USE_MOCKS=true and by the automated tests, never by the normal application.

import type {
  Dataset,
  Feature,
  FeatureCollection,
  FeatureType,
  Layer,
  Position,
  PriorityPreset,
  Priorities,
  PriorityPresetWeights,
  Region,
  RouteProfile,
  TerrainClass,
} from "@/types";

export const REGIONS: Region[] = [
  {
    id: 1,
    name: "Jezero Crater",
    bboxWest: 77.2,
    bboxSouth: 18.2,
    bboxEast: 77.7,
    bboxNorth: 18.7,
    coordinateSystem: "Mars 2000 geographic (IAU 49900), lon/lat degrees, east-positive",
    centerLon: 77.45,
    centerLat: 18.44,
    defaultZoom: 12,
    routableArea: null,
  },
];

export const DATASETS: Dataset[] = [
  {
    id: 1,
    name: "CTX digital terrain model — Jezero Crater (demo extract)",
    provider: "NASA / USGS Astrogeology",
    doi: null,
    url: "https://astrogeology.usgs.gov/",
    licence: "Public domain (NASA)",
    coverage: "Jezero Crater and western rim",
    coordinateSystem: "Mars 2000 geographic (IAU 49900)",
    format: "GeoTIFF",
    resolutionM: 20,
    accessedOn: "2026-10-01",
    isTraining: false,
  },
  {
    id: 2,
    name: "RedGrid demonstration feature catalogue",
    provider: "RedGrid prototype",
    doi: "10.5555/redgrid-demo-0001",
    url: "https://trek.nasa.gov/mars/",
    licence: "CC BY 4.0 (demonstration placeholder)",
    coverage: "Jezero Crater demo bounding box",
    coordinateSystem: "Mars 2000 geographic (IAU 49900)",
    format: "GeoJSON",
    resolutionM: 5,
    accessedOn: "2026-10-15",
    isTraining: false,
  },
  {
    id: 3,
    name: "Mars 2020 MEDA environment summary (demonstration)",
    provider: "NASA JPL (placeholder values)",
    doi: null,
    url: "https://mars.nasa.gov/mars2020/",
    licence: "Public domain (NASA)",
    coverage: "Jezero Crater floor, single station",
    coordinateSystem: "Mars 2000 geographic (IAU 49900)",
    format: "CSV",
    resolutionM: 1000,
    accessedOn: "2026-11-01",
    isTraining: false,
  },
];

const ds = (id: number) => {
  const d = DATASETS.find((x) => x.id === id)!;
  return { id: d.id, name: d.name, provider: d.provider };
};

export const LAYERS: Layer[] = [
  {
    id: 1,
    regionId: 1,
    key: "elevation",
    displayName: "Elevation",
    kind: "RASTER",
    dataState: "HISTORICAL_OBSERVATION",
    defaultOn: false,
    dataset: ds(1),
  },
  {
    id: 2,
    regionId: 1,
    key: "slope",
    displayName: "Slope",
    kind: "RASTER",
    dataState: "DERIVED",
    defaultOn: false,
    dataset: ds(1),
  },
  {
    id: 3,
    regionId: 1,
    key: "hillshade",
    displayName: "Hillshade",
    kind: "RASTER",
    dataState: "DERIVED",
    defaultOn: false,
    dataset: ds(1),
  },
  {
    id: 4,
    regionId: 1,
    key: "terrain-units",
    displayName: "Terrain units",
    kind: "VECTOR",
    dataState: "LIMITED_CONFIDENCE",
    defaultOn: false,
    dataset: ds(2),
  },
  {
    id: 5,
    regionId: 1,
    key: "hazards",
    displayName: "Hazards",
    kind: "VECTOR",
    dataState: "DEMONSTRATION_DATA",
    defaultOn: true,
    dataset: ds(2),
  },
  {
    id: 6,
    regionId: 1,
    key: "rim-scarps",
    displayName: "Crater rims and scarps",
    kind: "VECTOR",
    dataState: "DERIVED",
    defaultOn: false,
    dataset: ds(2),
  },
  {
    id: 7,
    regionId: 1,
    key: "science-targets",
    displayName: "Science targets",
    kind: "VECTOR",
    dataState: "DEMONSTRATION_DATA",
    defaultOn: true,
    dataset: ds(2),
  },
  {
    id: 8,
    regionId: 1,
    key: "safe-points",
    displayName: "Safe points",
    kind: "VECTOR",
    dataState: "DEMONSTRATION_DATA",
    defaultOn: true,
    dataset: ds(2),
  },
  {
    id: 9,
    regionId: 1,
    key: "communication",
    displayName: "Communication assets",
    kind: "VECTOR",
    dataState: "DEMONSTRATION_DATA",
    defaultOn: false,
    dataset: ds(2),
  },
  {
    id: 10,
    regionId: 1,
    key: "rover-path",
    displayName: "Rover path",
    kind: "VECTOR",
    dataState: "HISTORICAL_OBSERVATION",
    defaultOn: false,
    dataset: ds(2),
  },
];

let featureId = 100;
const props = (
  featureType: FeatureType,
  name: string,
  scienceValue: number | null = null,
  providesRefill: boolean | null = null,
) => ({
  id: ++featureId,
  featureType,
  name,
  code: null,
  scienceValue,
  providesRefill: featureType === "SAFE_POINT" ? (providesRefill ?? false) : null,
  heightM: null,
});
const point = (
  featureType: FeatureType,
  name: string,
  coordinates: Position,
  scienceValue: number | null = null,
  refill: boolean | null = null,
): Feature => ({
  type: "Feature",
  geometry: { type: "Point", coordinates },
  properties: props(featureType, name, scienceValue, refill),
});
const polygon = (
  featureType: FeatureType,
  name: string,
  ring: Position[],
  scienceValue: number | null = null,
): Feature => ({
  type: "Feature",
  geometry: { type: "Polygon", coordinates: [[...ring, ring[0]!]] },
  properties: props(featureType, name, scienceValue),
});
const line = (featureType: FeatureType, name: string, coordinates: Position[]): Feature => ({
  type: "Feature",
  geometry: { type: "LineString", coordinates },
  properties: props(featureType, name),
});
const fc = (features: Feature[]): FeatureCollection => ({ type: "FeatureCollection", features });

export const LAYER_FEATURES: Record<string, FeatureCollection> = {
  hazards: fc([
    point("HAZARD", "Boulder field B-3", [77.405, 18.468]),
    point("HAZARD", "Delta scarp edge", [77.472, 18.487]),
    point("HAZARD", "Loose regolith patch", [77.528, 18.414]),
    point("HAZARD", "Rim slump block", [77.362, 18.392]),
    point("HAZARD", "Aeolian ripple field", [77.458, 18.372]),
  ]),
  "science-targets": fc([
    point("SCIENCE_TARGET", "Delta front outcrop", [77.425, 18.492], 9),
    point("SCIENCE_TARGET", "Carbonate margin", [77.512, 18.461], 8),
    point("SCIENCE_TARGET", "Lakebed mudstones", [77.474, 18.423], 7),
    point("SCIENCE_TARGET", "Inlet channel deposit", [77.338, 18.517], 6),
  ]),
  "safe-points": fc([
    point("SAFE_POINT", "Landing Zone Alpha", [77.45, 18.44], null, true),
    point("SAFE_POINT", "Shelter cache 1", [77.392, 18.432]),
    point("SAFE_POINT", "Rover depot", [77.552, 18.482]),
  ]),
  communication: fc([
    point("COMMUNICATION_ASSET", "Relay mast", [77.438, 18.458]),
    point("COMMUNICATION_ASSET", "Ridge repeater", [77.571, 18.523]),
  ]),
  "rover-path": fc([
    {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [77.31, 18.362],
          [77.352, 18.381],
          [77.389, 18.405],
          [77.421, 18.429],
          [77.452, 18.446],
          [77.488, 18.458],
          [77.521, 18.477],
          [77.556, 18.501],
          [77.584, 18.531],
        ],
      },
      properties: props("ROVER_PATH", "Prior rover traverse"),
    },
  ]),
  "rim-scarps": fc([
    line("RIM_SCARP", "Exposed ridge edge", [
      [77.512, 18.372],
      [77.538, 18.368],
      [77.546, 18.388],
    ]),
    line("RIM_SCARP", "Plateau scarp", [
      [77.356, 18.488],
      [77.381, 18.484],
      [77.388, 18.506],
    ]),
  ]),
  "terrain-units": fc([
    polygon("TERRAIN_UNIT", "Western delta deposits", [
      [77.35, 18.46],
      [77.43, 18.47],
      [77.46, 18.51],
      [77.42, 18.55],
      [77.34, 18.54],
      [77.31, 18.5],
    ]),
    polygon("TERRAIN_UNIT", "Crater floor fractured unit", [
      [77.38, 18.36],
      [77.53, 18.35],
      [77.58, 18.42],
      [77.55, 18.47],
      [77.45, 18.46],
      [77.37, 18.42],
    ]),
    polygon("TERRAIN_UNIT", "Inner rim terraces", [
      [77.25, 18.3],
      [77.33, 18.27],
      [77.38, 18.33],
      [77.33, 18.4],
      [77.26, 18.38],
    ]),
  ]),
};

export const TERRAIN_CLASS_BY_UNIT: Record<string, TerrainClass> = {
  "Western delta deposits": "BEDROCK",
  "Crater floor fractured unit": "BEDROCK",
  "Inner rim terraces": "BOULDER_FIELD",
};

const rules = (
  scale: (number | null)[],
  maxFactor = [50, 20, 10, 10, 50, 2],
): RouteProfile["rules"] =>
  (["HAZARD", "TERRAIN", "SCIENCE", "COMMUNICATION", "UNCERTAINTY", "ROVER_PATH"] as const).map(
    (group, i) => ({
      group,
      scale: scale[i] ?? null,
      maxFactor: maxFactor[i]!,
      maxVsHazard: group === "SCIENCE" ? 1 : null,
    }),
  );

export const ROUTE_PROFILES: RouteProfile[] = [
  {
    key: "SAFEST",
    displayName: "Safest",
    distanceWeight: 0,
    rules: rules([2, 1.5, 0.5, 1.5, 1.5, 1]),
  },
  {
    key: "SHORTEST",
    displayName: "Shortest",
    distanceWeight: 1,
    rules: rules([0.5, 0.3, 0, 0, 1, 0]),
  },
  {
    key: "SCIENCE_FOCUSED",
    displayName: "Science-focused",
    distanceWeight: 0,
    rules: rules([1, 1, 2, 1, 1, 1]),
  },
  {
    key: "MISSION_PRIORITY",
    displayName: "Mission priority",
    distanceWeight: null,
    rules: rules([null, null, null, null, null, null]),
  },
];

/** Priorities the server fills in for each non-CUSTOM preset. */
export const PRESET_PRIORITIES: Record<Exclude<PriorityPreset, "CUSTOM">, Priorities> = {
  BALANCED: {
    safetyWeight: 0.5,
    scienceWeight: 0.5,
    distanceWeight: 0.5,
    walkingDifficultyWeight: 0.5,
    returnWeight: 0.5,
    environmentWeight: 0.5,
    roverPathWeight: 0.3,
  },
  SAFETY_FOCUSED: {
    safetyWeight: 1,
    scienceWeight: 0.3,
    distanceWeight: 0.3,
    walkingDifficultyWeight: 0.8,
    returnWeight: 0.9,
    environmentWeight: 0.7,
    roverPathWeight: 0.4,
  },
  SCIENCE_FOCUSED: {
    safetyWeight: 0.5,
    scienceWeight: 1,
    distanceWeight: 0.2,
    walkingDifficultyWeight: 0.4,
    returnWeight: 0.5,
    environmentWeight: 0.4,
    roverPathWeight: 0.2,
  },
  SHORTEST: {
    safetyWeight: 0.3,
    scienceWeight: 0.1,
    distanceWeight: 1,
    walkingDifficultyWeight: 0.3,
    returnWeight: 0.4,
    environmentWeight: 0.3,
    roverPathWeight: 0.5,
  },
};

export const MOCK_NOTICE =
  "Prototype human-mobility assumptions; not official NASA EVA limits. Demonstration data: every value in this report is a placeholder, not a real result.";

export const PRESET_FIXTURES: PriorityPresetWeights[] = (
  [
    ["BALANCED", "Balanced", "Every factor counts; none dominates"],
    ["SAFETY_FOCUSED", "Safety first", "Stay far from hazards and rough ground"],
    ["SCIENCE_FOCUSED", "Science first", "Pass as many science targets as is safe"],
    ["SHORTEST", "Shortest", "Least distance within the hard limits"],
  ] as const
).map(([key, displayName, description]) => ({
  key,
  displayName,
  description,
  basis: "TEST FIXTURE",
  weights: PRESET_PRIORITIES[key],
}));
