// Display-only scaling for the route radar chart. Never stored, sent to the API, or used to rank routes.

import type { Route } from "@/types";

export type Better = "lower" | "higher";

export interface RadarMetric {
  key: string;
  label: string;
  unit: string;
  better: Better;
  /** Original value from the API route object (null = missing; never replaced by 0). */
  get: (r: Route) => number | null;
  format: (v: number) => string;
}

const n = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? null : v;

export const RADAR_METRICS: RadarMetric[] = [
  {
    key: "distance",
    label: "Distance",
    unit: "km",
    better: "lower",
    get: (r) => (n(r.distanceM) === null ? null : r.distanceM! / 1000),
    format: (v) => `${v.toFixed(2)} km`,
  },
  {
    key: "duration",
    label: "Duration",
    unit: "min",
    better: "lower",
    get: (r) => n(r.durationMin),
    format: (v) => `${Math.round(v)} min`,
  },
  {
    key: "maxSlope",
    label: "Max slope",
    unit: "°",
    better: "lower",
    get: (r) => n(r.maxSlopeDeg),
    format: (v) => `${v.toFixed(1)}°`,
  },
  {
    key: "hazards",
    label: "Hazards",
    unit: "",
    better: "lower",
    get: (r) => n(r.hazardCount),
    format: (v) => `${v}`,
  },
  {
    key: "science",
    label: "Science",
    unit: "%",
    better: "higher",
    get: (r) => (n(r.scienceScore) === null ? null : r.scienceScore! * 100),
    format: (v) => `${Math.round(v)}%`,
  },
  {
    key: "match",
    label: "Mission match",
    unit: "%",
    better: "higher",
    get: (r) => n(r.missionMatch),
    format: (v) => `${v.toFixed(1)}%`,
  },
  {
    key: "o2Left",
    label: "O₂ left",
    unit: "kg",
    better: "higher",
    get: (r) => n(r.oxygenLeftKg),
    format: (v) => `${v.toFixed(3)} kg`,
  },
  {
    key: "confidence",
    label: "Data confidence",
    unit: "%",
    better: "higher",
    get: (r) =>
      n(r.assessment.dataConfidence) === null ? null : r.assessment.dataConfidence! * 100,
    format: (v) => `${Math.round(v)}%`,
  },
  {
    key: "gain",
    label: "Elevation gain",
    unit: "m",
    better: "lower",
    get: (r) => n(r.elevationGainM),
    format: (v) => `${Math.round(v)} m`,
  },
  {
    key: "terrain",
    label: "Terrain effort",
    unit: "×",
    better: "lower",
    get: (r) => n(r.terrainDifficulty),
    format: (v) => `${v.toFixed(2)}×`,
  },
  {
    key: "o2Used",
    label: "O₂ used",
    unit: "kg",
    better: "lower",
    get: (r) => n(r.oxygenUsedKg),
    format: (v) => `${v.toFixed(3)} kg`,
  },
  {
    key: "batteryLeft",
    label: "Battery left",
    unit: "Wh",
    better: "higher",
    get: (r) => n(r.batteryLeftWh),
    format: (v) => `${Math.round(v)} Wh`,
  },
  {
    key: "return",
    label: "Return time",
    unit: "min",
    better: "lower",
    get: (r) => n(r.returnFeasibility?.returnDurationMin),
    format: (v) => `${Math.round(v)} min`,
  },
];

export const DEFAULT_RADAR_KEYS = [
  "distance",
  "duration",
  "maxSlope",
  "hazards",
  "science",
  "match",
  "o2Left",
  "confidence",
];

/** A route the backend could not route at all: the drawn line is only the straight start–destination link. */
export const isNoPath = (r: Route) => r.warnings.some((w) => w.startsWith("No route found"));

export interface RadarRow {
  metric: RadarMetric;
  /** 0 to the observed maximum across the plotted routes (non-negative metrics). */
  max: number;
  allZero: boolean;
  /** routeId → display value 0..1 */
  scaled: Record<number, number>;
}

/**
 * Builds display rows: a metric is kept only if every plotted route has a value (missing values are never plotted
 * as zero) and every value is non-negative (O₂/battery left can go below zero on an infeasible route: such a metric
 * is left out rather than distorted). All-zero domains plot at 0 and are flagged.
 */
export function buildRadar(routes: Route[], keys: string[]) {
  const plotted = routes.filter((r) => !isNoPath(r));
  const notPlotted = routes.filter(isNoPath);
  const rows: RadarRow[] = [];
  const skipped: { metric: RadarMetric; reason: string }[] = [];
  for (const metric of RADAR_METRICS.filter((m) => keys.includes(m.key))) {
    const vals = plotted.map((r) => metric.get(r));
    if (!plotted.length) break;
    if (vals.some((v) => v === null)) {
      skipped.push({ metric, reason: "missing for at least one route" });
      continue;
    }
    if ((vals as number[]).some((v) => v < 0)) {
      skipped.push({ metric, reason: "negative for at least one route" });
      continue;
    }
    const max = Math.max(...(vals as number[]));
    const scaled: Record<number, number> = {};
    plotted.forEach((r, i) => (scaled[r.id] = max > 0 ? (vals[i] as number) / max : 0));
    rows.push({ metric, max, allZero: max === 0, scaled });
  }
  return { rows, plotted, notPlotted, skipped, enough: rows.length >= 3 && plotted.length > 0 };
}
