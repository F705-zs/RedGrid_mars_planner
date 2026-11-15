import { describe, expect, it } from "vitest";

import { buildCreateMissionBody, textureUrl } from "@/api/client";
import { layerGroup } from "@/lib/layer-groups";
import { appendFootstep, sceneToLonLat, SCENE_ORIGIN } from "@/lib/footsteps";
import { mixEntries, mixTotal, mixWeights, shareOf } from "@/lib/priorities";
import { buildRadar, DEFAULT_RADAR_KEYS, isNoPath } from "@/lib/radar";
import { fmtMultiplier, fmtShare, UNAVAILABLE } from "@/lib/format";
import type { Layer, Priorities, PriorityPresetWeights, Route } from "@/types";

const P = (o: Partial<Priorities> = {}): Priorities => ({
  safetyWeight: 0,
  scienceWeight: 0,
  distanceWeight: 0,
  walkingDifficultyWeight: 0,
  returnWeight: 0,
  environmentWeight: 0,
  roverPathWeight: 0,
  ...o,
});
const base = {
  regionId: 1,
  name: "Walk",
  startLon: 77.45,
  startLat: 18.44,
  destLon: 77.41,
  destLat: 18.45,
};

describe("RedGrid mission body", () => {
  it("presets never carry priorities or a mix; CUSTOM carries both", () => {
    const mix = [{ presetKey: "BALANCED" as const, percent: 100 }];
    const preset = buildCreateMissionBody({
      ...base,
      profile: "BALANCED",
      priorities: P({ safetyWeight: 1 }),
      priorityMix: mix,
    });
    expect(preset).not.toHaveProperty("priorities");
    expect(preset).not.toHaveProperty("priorityMix");
    const custom = buildCreateMissionBody({
      ...base,
      profile: "CUSTOM",
      priorities: P({ safetyWeight: 1 }),
      priorityMix: mix,
    });
    expect(custom.priorities?.safetyWeight).toBe(1);
    expect(custom.priorityMix).toEqual(mix);
  });

  it("leaves empty optional fields out so the backend defaults apply", () => {
    const b = buildCreateMissionBody({
      ...base,
      profile: "BALANCED",
      priorities: P(),
      objective: null,
      resources: {},
    });
    expect(b).not.toHaveProperty("objective");
    expect(b).not.toHaveProperty("resources");
  });
});

describe("custom priority mix", () => {
  const presets: PriorityPresetWeights[] = [
    {
      key: "BALANCED",
      displayName: "B",
      description: "",
      basis: "",
      weights: P({
        safetyWeight: 0.25,
        scienceWeight: 0.2,
        distanceWeight: 0.15,
        walkingDifficultyWeight: 0.15,
        returnWeight: 0.15,
        environmentWeight: 0.05,
        roverPathWeight: 0.05,
      }),
    },
    {
      key: "SCIENCE_FOCUSED",
      displayName: "S",
      description: "",
      basis: "",
      weights: P({
        safetyWeight: 0.2,
        scienceWeight: 0.45,
        distanceWeight: 0.05,
        walkingDifficultyWeight: 0.1,
        returnWeight: 0.1,
        environmentWeight: 0.05,
        roverPathWeight: 0.05,
      }),
    },
  ];
  it("is Σ percent/100 × preset weights (API Contract example: 60/40 → safety 0.23, science 0.30)", () => {
    const w = mixWeights({ BALANCED: 60, SCIENCE_FOCUSED: 40 }, presets)!;
    expect(w.safetyWeight).toBeCloseTo(0.23, 6);
    expect(w.scienceWeight).toBeCloseTo(0.3, 6);
    expect(mixTotal({ BALANCED: 60, SCIENCE_FOCUSED: 40 })).toBe(100);
    expect(mixEntries({ BALANCED: 60, SHORTEST: 0 })).toEqual([
      { presetKey: "BALANCED", percent: 60 },
    ]);
  });
  it("shows shares for display only", () => {
    expect(shareOf(P({ safetyWeight: 1, scienceWeight: 1 }), "safetyWeight")).toBe(0.5);
    expect(shareOf(P(), "safetyWeight")).toBeNull();
  });
});

describe("footsteps from the 3D walk", () => {
  it("maps the scene origin to the landing site and 1 km north to ~0.01687° of latitude", () => {
    expect(sceneToLonLat(0, 0)).toEqual([SCENE_ORIGIN.lon, SCENE_ORIGIN.lat]);
    const [, lat] = sceneToLonLat(0, 1000);
    expect(lat - SCENE_ORIGIN.lat).toBeCloseTo(0.016871, 5);
    const [lon] = sceneToLonLat(1000, 0);
    expect(lon - SCENE_ORIGIN.lon).toBeCloseTo(0.017784, 5); // 1 km east is wider in degrees at 18.4° N
  });
  it("keeps one point per 2 m", () => {
    const a = sceneToLonLat(0, 0);
    expect(appendFootstep([a], sceneToLonLat(0.5, 0))).toHaveLength(1);
    expect(appendFootstep([a], sceneToLonLat(3, 0))).toHaveLength(2);
  });
});

const route = (id: number, o: Partial<Route> = {}): Route =>
  ({
    id,
    missionId: 1,
    routeType: (["SAFEST", "SHORTEST", "SCIENCE_FOCUSED", "MISSION_PRIORITY"] as const)[id - 1]!,
    geometry: { type: "LineString", coordinates: [] },
    elevationProfile: [],
    feasible: true,
    overallRisk: "LOW",
    missionMatch: 90,
    distanceM: 4000,
    durationMin: 90,
    averageSlopeDeg: 3,
    maxSlopeDeg: 8,
    elevationGainM: 20,
    elevationLossM: 10,
    terrainDifficulty: 1.05,
    hazardCount: 0,
    scienceScore: 0.5,
    oxygenUsedKg: 0.1,
    batteryUsedWh: 100,
    oxygenLeftKg: 0.4,
    batteryLeftWh: 600,
    costModelId: 1,
    costModelVersion: 0,
    costProvider: {
      name: "a",
      kind: "ALGORITHM",
      transport: "LOCAL",
      version: "v0",
      status: "READY",
    },
    priorityResolver: {
      name: "a",
      kind: "ALGORITHM",
      transport: "LOCAL",
      version: "1",
      status: "READY",
    },
    window: null,
    calculatedAt: "",
    assessment: { dustStatus: "", communicationStatus: "", dataConfidence: 0.9 },
    returnFeasibility: null,
    warnings: [],
    recommendation: "",
    ...o,
  }) as Route;

describe("route radar (display-only scaling)", () => {
  it("scales each metric from 0 to the observed maximum and keeps the original values", () => {
    const rs = [route(1, { distanceM: 2000 }), route(2, { distanceM: 4000 })];
    const { rows } = buildRadar(rs, ["distance", "duration", "maxSlope"]);
    const d = rows.find((r) => r.metric.key === "distance")!;
    expect(d.max).toBe(4);
    expect(d.scaled[1]).toBe(0.5);
    expect(d.metric.get(rs[0]!)).toBe(2); // original km, untouched
    expect(rs[0]!.distanceM).toBe(2000); // route objects are not modified
  });
  it("flags all-zero domains instead of dividing by zero", () => {
    const { rows } = buildRadar(
      [route(1, { hazardCount: 0 }), route(2, { hazardCount: 0 })],
      ["hazards", "distance", "duration"],
    );
    const h = rows.find((r) => r.metric.key === "hazards")!;
    expect(h.allZero).toBe(true);
    expect(h.scaled[1]).toBe(0);
  });
  it("never plots a missing value as zero, and leaves out negative values", () => {
    const { rows, skipped } = buildRadar(
      [route(1, { oxygenLeftKg: null }), route(2, { batteryLeftWh: -20 })],
      ["o2Left", "batteryLeft", "distance", "duration", "maxSlope"],
    );
    expect(rows.map((r) => r.metric.key)).not.toContain("o2Left");
    expect(rows.map((r) => r.metric.key)).not.toContain("batteryLeft");
    expect(skipped.map((s) => s.metric.key)).toEqual(["o2Left", "batteryLeft"]);
  });
  it("does not draw a route that has no path, and reports insufficient data", () => {
    const noPath = route(3, {
      feasible: false,
      warnings: [
        "No route found: the line shown is the straight link between start and destination, not a walkable path",
      ],
    });
    expect(isNoPath(noPath)).toBe(true);
    const r = buildRadar([route(1), noPath], DEFAULT_RADAR_KEYS);
    expect(r.plotted.map((x) => x.id)).toEqual([1]);
    expect(r.notPlotted.map((x) => x.id)).toEqual([3]);
    expect(buildRadar([noPath], DEFAULT_RADAR_KEYS).enough).toBe(false);
    expect(buildRadar([route(1)], ["distance", "duration"]).enough).toBe(false);
  });
});

describe("RedGrid display formats keep missing values missing", () => {
  it("formats numeric terrain difficulty and data confidence", () => {
    expect(fmtMultiplier(1.067)).toBe("1.07× flat ground");
    expect(fmtShare(0.877)).toBe("88%");
    expect(fmtMultiplier(null)).toBe(UNAVAILABLE);
    expect(fmtShare(null)).toBe(UNAVAILABLE);
  });
});

describe("layer groups come from the key, not a fixed list", () => {
  const L = (key: string) => ({ key }) as Layer;
  it.each([
    ["imagery_hirise", "Imagery"],
    ["slope", "Terrain"],
    ["hazards", "Hazards"],
    ["rim_scarps", "Hazards"],
    ["science_targets", "Science"],
    ["comm_coverage", "Environment"],
    ["thermal_inertia", "Environment"],
    ["safe_points", "Mission context"],
    ["rover_path", "Mission context"],
    ["landing_ellipse", "Mission context"],
    ["something_new", "Terrain"],
  ])("%s → %s", (key, group) => expect(layerGroup(L(key))).toBe(group));
});

describe("texture URL (RedGrid raster overlay)", () => {
  it("asks the backend for exactly the bbox and clamps the size", () => {
    const u = new URL(
      textureUrl(1, "slope", { west: 77.4, south: 18.4, east: 77.5, north: 18.5 }, 5000),
    );
    expect(u.pathname.endsWith("/regions/1/terrain/texture")).toBe(true);
    expect(u.searchParams.get("layer")).toBe("slope");
    expect(u.searchParams.get("size")).toBe("2048");
    expect(u.searchParams.get("west")).toBe("77.400000");
  });
});
