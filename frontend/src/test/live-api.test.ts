/**
 * Contract test against a RUNNING RedGrid backend (skipped unless RG_LIVE_API is set):
 *   RG_LIVE_API=1 VITE_API_BASE_URL=http://127.0.0.1:5000/api bun run test src/test/live-api.test.ts
 * Every call goes through the app's own API client, and the answers are passed through the same formatting and
 * radar code the pages use, so a contract mismatch fails here instead of on screen.
 */
import { describe, expect, it } from "vitest";

import { api, buildCreateMissionBody, isApiError, textureUrl } from "@/api/client";
import { fmtDistance, fmtDuration, fmtKg, fmtMultiplier, fmtShare, fmtSlope, fmtWh } from "@/lib/format";
import { layerGroup } from "@/lib/layer-groups";
import { mixWeights } from "@/lib/priorities";
import { buildRadar, DEFAULT_RADAR_KEYS } from "@/lib/radar";
import type { Mission, Route } from "@/types";
import { ROUTE_TYPES } from "@/types";

const live = !!(globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env["RG_LIVE_API"];
const LANDING = { lon: 77.45088573, lat: 18.44462715 };
const DEST = { lon: 77.38330584, lat: 18.46993306 };

async function code(p: Promise<unknown>) {
  try {
    await p;
    return "OK";
  } catch (e) {
    return isApiError(e) ? e.code : String(e);
  }
}

function renderCard(r: Route) {
  // exactly the fields RouteCard / report / radar read
  return [
    fmtDistance(r.distanceM), fmtDuration(r.durationMin), fmtSlope(r.maxSlopeDeg), fmtShare(r.scienceScore),
    fmtMultiplier(r.terrainDifficulty), fmtKg(r.oxygenLeftKg), fmtWh(r.batteryLeftWh), fmtShare(r.assessment.dataConfidence),
    r.costProvider.name, r.costProvider.version, r.returnFeasibility?.limitingResource ?? "none",
  ];
}

describe.skipIf(!live)("live RedGrid API (RedGrid)", () => {
  let mission: Mission;
  let routes: Route[];

  it("catalog endpoints match the contract the pages use", async () => {
    const regions = await api.getRegions();
    expect(regions[0]!.routableArea?.type).toBe("Polygon");
    const layers = await api.getLayers(1);
    expect(layers.length).toBeGreaterThan(10);
    for (const l of layers.filter((x) => x.kind === "VECTOR")) {
      const fc = await api.getLayerGeojson(1, l.key);
      expect(fc.type).toBe("FeatureCollection");
      expect(layerGroup(l)).toBeTruthy();
    }
    expect((await api.getDatasets(1)).some((d) => d.url === null)).toBe(true); // team data: drawer must cope
    expect((await api.getPriorityPresets()).map((p) => p.key)).toEqual(["BALANCED", "SAFETY_FOCUSED", "SCIENCE_FOCUSED", "SHORTEST"]);
    expect((await api.getRouteProfiles()).every((p) => p.rules.length === 6)).toBe(true);
    expect((await api.getPlanningConstants()).find((c) => c.key === "default_oxygen_kg")?.value).toBe(0.6);
    expect(["DEMONSTRATION_DATA", "HISTORICAL_OBSERVATION"]).toContain((await api.getDemoWindow())?.dataState);
    expect((await api.getProviders()).cost.at(-1)?.kind).toBe("ALGORITHM");
    const grid = await api.getTerrain(1, { west: 77.43, south: 18.43, east: 77.47, north: 18.46 }, 32);
    expect(grid.elevations.length).toBe(grid.width * grid.height);
  });

  it("raster overlays and imagery fallback answer as the map expects", async () => {
    const box = { west: 77.43, south: 18.43, east: 77.47, north: 18.46 };
    const png = await fetch(textureUrl(1, "slope", box, 256));
    expect(png.status).toBe(200);
    expect(png.headers.get("content-type")).toBe("image/png");
    // Real prepared data returns 200 image/png; synthetic demo data without orthomosaics returns 503
    expect([200, 503]).toContain((await fetch(textureUrl(1, "imagery_hirise", box, 256))).status);
    expect([200, 503]).toContain((await fetch(textureUrl(1, "imagery_ctx", box, 256))).status);
  });

  it("location panel fields", async () => {
    const inside = await api.getLocation(1, LANDING.lon, LANDING.lat);
    expect(inside.routable).toBe(true);
    expect(inside.nearestRefillPoint?.providesRefill).toBe(true);
    expect(["DATA_UNAVAILABLE", "HISTORICAL_OBSERVATION"]).toContain(inside.environment.dataState);
    const outside = await api.getLocation(1, 77.21, 18.21);
    expect(outside.routable).toBe(false);
    expect(outside.slopeDeg).toBeNull(); // missing stays missing
  });

  it("mission setup: custom mix + objective + resources; client mix equals the backend's", async () => {
    const presets = await api.getPriorityPresets();
    const mix = { BALANCED: 60, SCIENCE_FOCUSED: 40 } as const;
    const local = mixWeights(mix, presets)!;
    mission = await api.createMission(
      buildCreateMissionBody({
        regionId: 1, name: "Live contract test", objective: "Reach the delta", startLon: LANDING.lon, startLat: LANDING.lat,
        destLon: DEST.lon, destLat: DEST.lat, profile: "CUSTOM", priorities: local,
        priorityMix: [{ presetKey: "BALANCED", percent: 60 }, { presetKey: "SCIENCE_FOCUSED", percent: 40 }],
        startIsBase: true, resources: { oxygenKg: 0.6, batteryWh: 800 },
      }),
    );
    expect(mission.objective).toBe("Reach the delta");
    expect(mission.priorityMix).toHaveLength(2);
    expect(mission.priorities.safetyWeight).toBeCloseTo(local.safetyWeight, 5);
    const res = await api.getResources(mission.id);
    expect(res.oxygenKg.source).toBe("USER_INPUT");
    expect(res.metabolicRateW.source).toBe("DEFAULT_ASSUMPTION");
  });

  it("routes: every card field renders and the radar has enough data", async () => {
    routes = await api.calculateRoutes(mission.id);
    expect(routes.map((r) => r.routeType).sort()).toEqual([...ROUTE_TYPES].sort());
    routes.forEach((r) => expect(() => renderCard(r)).not.toThrow());
    const radar = buildRadar(routes, DEFAULT_RADAR_KEYS);
    expect(radar.enough).toBe(true);
    expect(radar.rows.length).toBeGreaterThanOrEqual(6);
    expect((await api.getRoutes(mission.id)).map((r) => r.id).sort()).toEqual(routes.map((r) => r.id).sort());
  });

  it("edit, recalculate, select, report", async () => {
    const a = await api.createAnnotation(mission.id, { kind: "SCIENCE_STOP", lon: 77.43, lat: 18.45, note: "stop", durationMin: 20 });
    await api.deleteAnnotation(mission.id, a.id);
    const again = await api.recalculateRoutes(mission.id);
    expect(again[0]!.id).not.toBe(routes[0]!.id); // ids change on recalculation (contract)
    const feasible = again.find((r) => r.feasible)!;
    expect((await api.selectRoute(mission.id, feasible.id)).selectedRouteId).toBe(feasible.id);
    const report = await api.getReport(mission.id);
    expect(report.recommendedRoute?.id).toBe(feasible.id);
    expect(report.caveats.length).toBeGreaterThan(0);
    expect(report.providersUsed.length).toBeGreaterThan(0);
    expect(report.resources.oxygenKg.value).toBe(0.6);
    expect(await api.setResources(mission.id, { batteryWh: 900 })).toHaveProperty("batteryWh.value", 900);
  });

  it("status flow, duplicate and the errors the UI handles", async () => {
    expect(await code(api.setMissionStatus(mission.id, "FINALIZED"))).toBe("INVALID_STATUS_TRANSITION");
    await api.setMissionStatus(mission.id, "PLANNED");
    await api.setMissionStatus(mission.id, "FINALIZED");
    expect(await code(api.patchMission(mission.id, { name: "x" }))).toBe("MISSION_FINALIZED");
    expect((await api.duplicateMission(mission.id)).status).toBe("DRAFT");
    const bad = { regionId: 1, name: "x", startLon: LANDING.lon, startLat: LANDING.lat, profile: "BALANCED" as const };
    expect(await code(api.createMission({ ...bad, destLon: 77.21, destLat: 18.21 }))).toBe("OUT_OF_COVERAGE");
    expect(await code(api.createMission({ ...bad, destLon: 78, destLat: 18.4 }))).toBe("OUT_OF_REGION");
    expect(await code(api.getMission(999999))).toBe("MISSION_NOT_FOUND");
    expect((await api.getMissions()).length).toBeGreaterThan(1);
  });
});

describe.skipIf(live)("live RedGrid API (RedGrid)", () => {
  it("is skipped without RG_LIVE_API", () => expect(true).toBe(true));
});
