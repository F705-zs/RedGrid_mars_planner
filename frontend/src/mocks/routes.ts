// Placeholder route generator for mock mode: four plausible LineStrings between start
// and destination with different metrics. Not real routing results.

import { distanceM, distanceToLineM, lineLengthM, MARS_RADIUS_M, offsetM } from "@/lib/geo";
import type {
  Annotation,
  Mission,
  Position,
  ReturnFeasibility,
  RiskLevel,
  Route,
  RouteType,
} from "@/types";
import { ROUTE_TYPES } from "@/types";

import { elevationAt, featuresOfType, nearest, slopeAt } from "./terrain";

const WALK_M_PER_MIN = 2_000 / 60; // 2 km/h placeholder walking speed
export const MAX_SLOPE_LIMIT_DEG = 25;

function localXY(origin: Position, p: Position) {
  const kx = MARS_RADIUS_M * Math.cos((origin[1] * Math.PI) / 180) * (Math.PI / 180);
  const ky = MARS_RADIUS_M * (Math.PI / 180);
  return { x: (p[0] - origin[0]) * kx, y: (p[1] - origin[1]) * ky };
}

/** Densified polyline through waypoints with a sideways bulge of `bulge` × segment length. */
function curvedPath(waypoints: Position[], bulge: number, samplesPerSegment = 12): Position[] {
  const out: Position[] = [waypoints[0]!];
  for (let s = 1; s < waypoints.length; s++) {
    const a = waypoints[s - 1]!;
    const b = waypoints[s]!;
    const { x, y } = localXY(a, b);
    const len = Math.hypot(x, y) || 1;
    const nx = -y / len;
    const ny = x / len;
    for (let i = 1; i <= samplesPerSegment; i++) {
      const t = i / samplesPerSegment;
      const base: Position = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
      const off = Math.sin(Math.PI * t) * bulge * len + Math.sin(t * Math.PI * 5) * len * 0.008;
      out.push(i === samplesPerSegment ? b : offsetM(base, nx * off, ny * off));
    }
  }
  return out.map(([lon, lat]) => [Math.round(lon * 1e6) / 1e6, Math.round(lat * 1e6) / 1e6]);
}

/** Orders points by how far along start→dest they project. */
function orderAlong(start: Position, dest: Position, pts: Position[]) {
  const d = localXY(start, dest);
  const len2 = d.x * d.x + d.y * d.y || 1;
  return [...pts].sort((p, q) => {
    const a = localXY(start, p);
    const b = localXY(start, q);
    return (a.x * d.x + a.y * d.y) / len2 - (b.x * d.x + b.y * d.y) / len2;
  });
}

function geometryFor(
  type: RouteType,
  start: Position,
  dest: Position,
  stops: Position[],
): Position[] {
  switch (type) {
    case "SHORTEST":
      return curvedPath([start, dest], 0.01);
    case "SAFEST":
      return curvedPath([start, dest], 0.24);
    case "MISSION_PRIORITY":
      return curvedPath([start, ...orderAlong(start, dest, stops), dest], -0.1);
    case "SCIENCE_FOCUSED": {
      const direct = distanceM(start, dest);
      const targets = featuresOfType("SCIENCE_TARGET")
        .map((f) => ({ p: f.geometry.coordinates as Position, v: f.properties.scienceValue ?? 0 }))
        .map((t) => ({ ...t, detour: distanceM(start, t.p) + distanceM(t.p, dest) - direct }))
        .filter((t) => t.detour < direct * 0.9 + 4_000)
        .sort((a, b) => b.v / (1 + b.detour / 2_000) - a.v / (1 + a.detour / 2_000))
        .slice(0, 1)
        .map((t) => t.p);
      return curvedPath([start, ...orderAlong(start, dest, [...targets, ...stops]), dest], 0.06);
    }
  }
}

const riskFromScore = (s: number): RiskLevel =>
  s < 35 ? "LOW" : s < 60 ? "MODERATE" : s < 85 ? "HIGH" : "CRITICAL";
const RISK_RANK: Record<RiskLevel, number> = { LOW: 0, MODERATE: 1, HIGH: 2, CRITICAL: 3 };

export function generateRoutes(
  mission: Mission,
  annotations: Annotation[],
  nextId: () => number,
): Route[] {
  const start: Position = [mission.startLon, mission.startLat];
  const dest: Position = [mission.destLon, mission.destLat];
  const stops = annotations
    .filter((a) => a.kind === "SCIENCE_STOP")
    .map((a) => [a.lon, a.lat] as Position);
  const warnings = annotations.filter((a) => a.kind === "HAZARD_WARNING");
  const hazards = featuresOfType("HAZARD").map((f) => f.geometry.coordinates as Position);
  const science = featuresOfType("SCIENCE_TARGET");
  const comms = featuresOfType("COMMUNICATION_ASSET").map(
    (f) => f.geometry.coordinates as Position,
  );
  const rover = featuresOfType("ROVER_PATH")[0]?.geometry;
  const roverLine = rover?.type === "LineString" ? rover.coordinates : [];
  const direct = distanceM(start, dest);
  const p = mission.priorities;

  return ROUTE_TYPES.map((routeType) => {
    const coords = geometryFor(routeType, start, dest, stops);
    const length = lineLengthM(coords);
    const warn: string[] = [];

    let unknown = 0;
    let slopeSum = 0;
    let slopeN = 0;
    let maxSlope = 0;
    let gain = 0;
    let loss = 0;
    let prevElev: number | null = null;
    for (const [lon, lat] of coords) {
      const s = slopeAt(lon, lat);
      const e = elevationAt(lon, lat);
      if (s === null || e === null) unknown++;
      if (s !== null) {
        slopeSum += s;
        slopeN++;
        maxSlope = Math.max(maxSlope, s);
      }
      if (e !== null && prevElev !== null) {
        if (e > prevElev) gain += e - prevElev;
        else loss += prevElev - e;
      }
      if (e !== null) prevElev = e;
    }
    let avgSlope = slopeN ? slopeSum / slopeN : 0;
    if (routeType === "SHORTEST") {
      maxSlope = Math.max(maxSlope, 27.5);
      warn.push(`Crosses a scarp steeper than the ${MAX_SLOPE_LIMIT_DEG}° walking limit.`);
    } else {
      maxSlope = Math.min(maxSlope, routeType === "SAFEST" ? 14 : 22);
      avgSlope = Math.min(avgSlope, maxSlope * 0.6);
    }
    if (unknown > 0)
      warn.push(`${unknown} sample points have no elevation data; slope there is unknown.`);

    const nearHazards = hazards.filter(
      (h) => distanceToLineM(h, coords) < (routeType === "SAFEST" ? 120 : 250),
    ).length;
    const crossedWarnings = warnings.filter(
      (w) => distanceToLineM([w.lon, w.lat], coords) <= (w.radiusM ?? 0),
    );
    crossedWarnings.forEach((w) =>
      warn.push(
        `Passes through hazard warning "${w.note || "unnamed"}" (${w.severity ?? "unknown"} severity).`,
      ),
    );
    const hazardCount = nearHazards + crossedWarnings.length;
    if (nearHazards > 0)
      warn.push(
        `${nearHazards} mapped hazard${nearHazards > 1 ? "s" : ""} within walking distance of the line.`,
      );

    const visitedStops = stops.filter((s) => distanceToLineM(s, coords) < 200);
    const stopMinutes = annotations
      .filter(
        (a) =>
          a.kind === "SCIENCE_STOP" && visitedStops.some((s) => s[0] === a.lon && s[1] === a.lat),
      )
      .reduce((sum, a) => sum + (a.durationMin ?? 0), 0);
    const nearScience = science.filter(
      (f) => distanceToLineM(f.geometry.coordinates as Position, coords) < 400,
    );
    const scienceScore = Math.min(
      100,
      Math.round(
        nearScience.reduce((s, f) => s + (f.properties.scienceValue ?? 0) * 9, 0) +
          visitedStops.length * 8,
      ),
    );

    const highWarnings = crossedWarnings.filter((w) => w.severity === "HIGH").length;
    let riskScore =
      (maxSlope / MAX_SLOPE_LIMIT_DEG) * 40 +
      hazardCount * 14 +
      highWarnings * 20 +
      (unknown ? 8 : 0);
    if (routeType === "SAFEST") riskScore *= 0.6;
    const feasible = maxSlope <= MAX_SLOPE_LIMIT_DEG && length <= 40_000;
    let overallRisk = riskFromScore(riskScore);
    if (!feasible && RISK_RANK[overallRisk] < RISK_RANK.HIGH) overallRisk = "HIGH";

    const durationMin = Math.round(
      (length / WALK_M_PER_MIN) * (1 + avgSlope / 30) +
        stopMinutes +
        nearScience.length * (routeType === "SCIENCE_FOCUSED" ? 20 : 0),
    );

    let returnFeasibility: ReturnFeasibility | null = null;
    if (routeType !== "SCIENCE_FOCUSED") {
      const safe = nearest("SAFE_POINT", dest);
      const maxReturn = Math.round(6_000 + p.returnWeight * 8_000);
      const dist = safe?.distanceM ?? 0;
      const ok = dist <= maxReturn;
      returnFeasibility = {
        feasible: ok,
        distanceToSafePointM: dist,
        returnDurationMin: Math.round(dist / WALK_M_PER_MIN),
        maximumReturnDistanceM: maxReturn,
        safePointName: safe?.feature.name ?? "None",
        reason: ok
          ? `Return to ${safe?.feature.name} fits within the reserved return budget.`
          : `Return to ${safe?.feature.name} exceeds the reserved return budget.`,
        limitingResource: "NONE",
        refillPointName: safe?.feature.name ?? null,
      };
      if (!ok) warn.push("Return to the nearest safe point exceeds the return budget.");
    }

    const commsFar = coords.some((c) => comms.every((a) => distanceM(c, a) > 7_000));
    const roverAvg = roverLine.length
      ? coords.reduce((s, c) => s + distanceToLineM(c, roverLine), 0) / coords.length
      : 5_000;

    const scores = {
      safetyWeight: 100 - Math.min(100, riskScore),
      scienceWeight: scienceScore,
      distanceWeight: (100 * direct) / Math.max(length, 1),
      walkingDifficultyWeight: 100 - Math.min(100, avgSlope * 5),
      returnWeight: returnFeasibility ? (returnFeasibility.feasible ? 90 : 30) : 50,
      environmentWeight: commsFar ? 55 : 80,
      roverPathWeight: 100 - Math.min(100, roverAvg / 40),
    };
    const wSum = Object.values(p).reduce((s, w) => s + w, 0) || 1;
    let missionMatch = Math.round(
      (Object.keys(scores) as (keyof typeof scores)[]).reduce((s, k) => s + p[k] * scores[k], 0) /
        wSum,
    );
    if (!feasible) missionMatch = Math.min(missionMatch, 30);

    const recommendation = !feasible
      ? "Not recommended: exceeds walking limits. Kept for comparison only."
      : routeType === "SAFEST"
        ? "Recommended when crew safety outweighs time; widest margin to mapped hazards."
        : routeType === "SCIENCE_FOCUSED"
          ? "Recommended for sampling; return to a safe point has not been checked."
          : routeType === "MISSION_PRIORITY"
            ? "Best overall fit to the mission priorities."
            : "Fastest option.";

    return {
      id: nextId(),
      missionId: mission.id,
      routeType,
      geometry: { type: "LineString", coordinates: coords },
      feasible,
      overallRisk,
      missionMatch: Math.max(0, Math.min(100, missionMatch)),
      distanceM: Math.round(length),
      durationMin,
      averageSlopeDeg: Math.round(avgSlope * 10) / 10,
      maxSlopeDeg: Math.round(maxSlope * 10) / 10,
      elevationGainM: Math.round(gain),
      elevationLossM: Math.round(loss),
      terrainDifficulty: Math.round((1 + avgSlope / 30) * 100) / 100,
      hazardCount,
      scienceScore: scienceScore / 100,
      // Fixtures have no oxygen / battery model: left missing, never invented
      elevationProfile: [],
      oxygenUsedKg: null,
      batteryUsedWh: null,
      oxygenLeftKg: null,
      batteryLeftWh: null,
      costModelId: 1,
      costModelVersion: 0,
      costProvider: {
        name: "test-fixture",
        kind: "ALGORITHM",
        transport: "LOCAL",
        version: "fixture",
        status: "READY",
      },
      priorityResolver: {
        name: "test-fixture",
        kind: "ALGORITHM",
        transport: "LOCAL",
        version: "fixture",
        status: "READY",
      },
      window: null,
      calculatedAt: "2026-11-01T00:00:00Z",
      assessment: {
        dustStatus: "Low dust activity (modelled)",
        communicationStatus: commsFar ? "Intermittent relay coverage" : "Line of sight to relay",
        dataConfidence: unknown ? 0.6 : 0.85,
      },
      returnFeasibility,
      warnings: warn,
      recommendation,
    };
  });
}
