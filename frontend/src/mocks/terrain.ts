// Deterministic placeholder terrain + location model for mock mode. Not real Mars data.

import { distanceM, pointInRing } from "@/lib/geo";
import type {
  EnvironmentalSnapshot,
  Feature,
  FeatureType,
  LocationInfo,
  NearFeature,
  Position,
  Region,
} from "@/types";

import { LAYER_FEATURES, TERRAIN_CLASS_BY_UNIT } from "./data";

const CENTER: Position = [77.45, 18.44];
const M_PER_DEG_LAT = 59_158; // Mars

/** Area with no elevation coverage, to exercise "Data unavailable" handling. */
export function inDataGap(lon: number, lat: number) {
  return lon > 77.63 && lat > 18.62;
}

/** Placeholder elevation in metres (MOLA-like datum), or null inside the data gap. */
export function elevationAt(lon: number, lat: number): number | null {
  if (inDataGap(lon, lat)) return null;
  const r = distanceM([lon, lat], CENTER);
  const rim = 320 * Math.exp(-(((r - 12_500) / 1_800) ** 2));
  const delta = 140 * Math.exp(-((distanceM([lon, lat], [77.4, 18.5]) / 3_500) ** 2));
  const rough = 18 * Math.sin(lon * 900) * Math.cos(lat * 760) + 9 * Math.sin((lon + lat) * 2_100);
  return Math.round((-2_560 + rim + delta + rough) * 10) / 10;
}

/** Placeholder slope in degrees from the elevation gradient, or null in the data gap. */
export function slopeAt(lon: number, lat: number): number | null {
  const d = 0.0006;
  const e0 = elevationAt(lon, lat);
  const ex = elevationAt(lon + d, lat);
  const ey = elevationAt(lon, lat + d);
  if (e0 === null || ex === null || ey === null) return null;
  const dx = d * M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
  const dy = d * M_PER_DEG_LAT;
  const g = Math.hypot((ex - e0) / dx, (ey - e0) / dy);
  return Math.round(Math.min(34, (Math.atan(g) * 180) / Math.PI) * 10) / 10;
}

export function featuresOfType(type: FeatureType): Feature[] {
  return Object.values(LAYER_FEATURES)
    .flatMap((c) => c.features)
    .filter((f) => f.properties.featureType === type);
}

function representativePoint(f: Feature): Position {
  const g = f.geometry;
  if (g.type === "Point") return g.coordinates;
  if (g.type === "LineString") return g.coordinates[Math.floor(g.coordinates.length / 2)]!;
  if (g.type === "Polygon") {
    const ring = g.coordinates[0]!;
    const n = ring.length - 1;
    return [
      ring.slice(0, n).reduce((s, p) => s + p[0], 0) / n,
      ring.slice(0, n).reduce((s, p) => s + p[1], 0) / n,
    ];
  }
  return CENTER;
}

export function nearest(
  type: FeatureType,
  p: Position,
): { feature: NearFeature; distanceM: number } | null {
  let best: { feature: NearFeature; distanceM: number } | null = null;
  for (const f of featuresOfType(type)) {
    const d = distanceM(p, representativePoint(f));
    if (!best || d < best.distanceM)
      best = {
        feature: {
          id: f.properties.id,
          featureType: type,
          name: f.properties.name,
          code: f.properties.code,
          providesRefill: f.properties.providesRefill,
          geometry: f.geometry,
        },
        distanceM: Math.round(d),
      };
  }
  return best;
}

export function terrainUnitAt(p: Position): string | null {
  const unit = featuresOfType("TERRAIN_UNIT").find(
    (f) => f.geometry.type === "Polygon" && pointInRing(p, f.geometry.coordinates[0]!),
  );
  return unit?.properties.name ?? null;
}

export function environmentSnapshot(regionId: number): EnvironmentalSnapshot {
  return {
    regionId,
    temperature: -61.8,
    pressure: 738,
    windSpeed: null, // anemometer gap in the demonstration record
    dustStatus: "LOW",
    solsWithData: 30,
    window: { startSol: 1700, endSol: 1729 },
    observedAt: "2026-11-10T13:00:00Z",
    dataState: "MODELLED_CONDITION",
    source: "MEDA environment summary (demonstration)",
  };
}

export function locationInfo(region: Region, lon: number, lat: number): LocationInfo {
  const p: Position = [lon, lat];
  const gap = inDataGap(lon, lat);
  const unit = terrainUnitAt(p);
  const hazard = nearest("HAZARD", p);
  const science = nearest("SCIENCE_TARGET", p);
  const safe = nearest("SAFE_POINT", p);
  return {
    lon,
    lat,
    routable: !gap,
    elevationM: elevationAt(lon, lat),
    slopeDeg: slopeAt(lon, lat),
    roughnessM: null,
    terrainUnit: unit,
    terrainClass: unit ? (TERRAIN_CLASS_BY_UNIT[unit] ?? null) : null,
    terrainClassDataState: "LIMITED_CONFIDENCE",
    categories: [],
    nearestHazard: hazard?.feature ?? null,
    nearestScienceTarget: science?.feature ?? null,
    nearestSafePoint: safe?.feature ?? null,
    nearestRefillPoint: null,
    distanceToNearestHazardM: hazard?.distanceM ?? null,
    distanceToNearestScienceTargetM: science?.distanceM ?? null,
    distanceToNearestSafePointM: safe?.distanceM ?? null,
    distanceToNearestRefillPointM: null,
    environment: environmentSnapshot(region.id),
    dataState: gap ? "LIMITED_CONFIDENCE" : "DEMONSTRATION_DATA",
    dataQuality: gap ? "LOW" : "MEDIUM",
  };
}
