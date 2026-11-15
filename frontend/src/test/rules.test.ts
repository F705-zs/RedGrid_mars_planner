import { beforeEach, describe, expect, it } from "vitest";

import { buildCreateMissionBody } from "@/api/client";
import { fmtDistance, fmtNumber, fmtSlope, fmtText, UNAVAILABLE } from "@/lib/format";
import { toLatLng } from "@/lib/geo";
import { canTransition } from "@/lib/mission-status";
import { allPrioritiesZero } from "@/lib/priorities";
import { resetDb } from "@/mocks/db";
import { handleMock } from "@/mocks/handlers";
import type { Mission, Priorities, Route } from "@/types";

const zero: Priorities = {
  safetyWeight: 0,
  scienceWeight: 0,
  distanceWeight: 0,
  walkingDifficultyWeight: 0,
  returnWeight: 0,
  environmentWeight: 0,
  roverPathWeight: 0,
};
const base = {
  regionId: 1,
  name: "Test walk",
  startLon: 77.45,
  startLat: 18.44,
  destLon: 77.42,
  destLat: 18.49,
};

const create = (body: object) => handleMock("POST", "/missions", body);
const errCode = (r: { body: unknown }) => (r.body as { error: { code: string } }).error.code;

beforeEach(() => resetDb());

describe("mission status transitions", () => {
  it("allows DRAFT→PLANNED, PLANNED→FINALIZED and PLANNED→DRAFT only", () => {
    expect(canTransition("DRAFT", "PLANNED")).toBe(true);
    expect(canTransition("PLANNED", "FINALIZED")).toBe(true);
    expect(canTransition("PLANNED", "DRAFT")).toBe(true);
    expect(canTransition("DRAFT", "FINALIZED")).toBe(false);
    expect(canTransition("FINALIZED", "PLANNED")).toBe(false);
    expect(canTransition("FINALIZED", "DRAFT")).toBe(false);
  });

  it("mock API rejects DRAFT→FINALIZED with 409 INVALID_STATUS_TRANSITION", () => {
    const m = create({ ...base, profile: "BALANCED" }).body as Mission;
    const r = handleMock("PATCH", `/missions/${m.id}/status`, { status: "FINALIZED" });
    expect(r.status).toBe(409);
    expect(errCode(r)).toBe("INVALID_STATUS_TRANSITION");
  });
});

describe("coordinates", () => {
  it("converts API [lon, lat] to Leaflet [lat, lon]", () => {
    expect(toLatLng([77.45, 18.44])).toEqual([18.44, 77.45]);
  });
});

describe("priorities", () => {
  it("sends priorities only for CUSTOM", () => {
    const p = { ...zero, safetyWeight: 1 };
    expect(
      buildCreateMissionBody({ ...base, profile: "BALANCED", priorities: p }),
    ).not.toHaveProperty("priorities");
    expect(
      buildCreateMissionBody({ ...base, profile: "CUSTOM", priorities: p }).priorities,
    ).toEqual(p);
  });

  it("blocks CUSTOM when all seven weights are zero", () => {
    expect(allPrioritiesZero(zero)).toBe(true);
    expect(allPrioritiesZero({ ...zero, roverPathWeight: 0.05 })).toBe(false);
    const r = create({ ...base, profile: "CUSTOM", priorities: zero });
    expect(r.status).toBe(400);
    expect(errCode(r)).toBe("VALIDATION_ERROR");
  });

  it("server fills priorities for presets", () => {
    const m = create({ ...base, profile: "SAFETY_FOCUSED" }).body as Mission;
    expect(m.priorities.safetyWeight).toBe(1);
    expect(m.status).toBe("DRAFT");
  });
});

describe("routes", () => {
  it("returns one route per type with one not feasible and one unchecked return", () => {
    const m = create({ ...base, profile: "BALANCED" }).body as Mission;
    const r = handleMock("POST", `/missions/${m.id}/routes`);
    const routes = r.body as Route[];
    expect(r.status).toBe(201);
    expect(routes.map((x) => x.routeType).sort()).toEqual([
      "MISSION_PRIORITY",
      "SAFEST",
      "SCIENCE_FOCUSED",
      "SHORTEST",
    ]);
    expect(routes.filter((x) => !x.feasible)).toHaveLength(1);
    expect(routes.filter((x) => x.returnFeasibility === null)).toHaveLength(1);
  });

  it("recalculate clears the selected route", () => {
    const m = create({ ...base, profile: "BALANCED" }).body as Mission;
    const routes = handleMock("POST", `/missions/${m.id}/routes`).body as Route[];
    handleMock("PUT", `/missions/${m.id}/selected-route`, { routeId: routes[0]!.id });
    expect((handleMock("GET", `/missions/${m.id}`).body as Mission).selectedRouteId).toBe(
      routes[0]!.id,
    );
    handleMock("POST", `/missions/${m.id}/routes/recalculate`);
    expect((handleMock("GET", `/missions/${m.id}`).body as Mission).selectedRouteId).toBeNull();
  });

  it("finalized missions reject edits with 409 MISSION_FINALIZED", () => {
    const finalized = (handleMock("GET", "/missions?status=FINALIZED").body as Mission[])[0]!;
    const r = handleMock("POST", `/missions/${finalized.id}/annotations`, {
      kind: "SCIENCE_STOP",
      lon: 77.45,
      lat: 18.44,
      note: "x",
      durationMin: 10,
    });
    expect(r.status).toBe(409);
    expect(errCode(r)).toBe("MISSION_FINALIZED");
  });

  it("rejects a start outside the region with OUT_OF_REGION", () => {
    const r = create({ ...base, startLon: 80, profile: "BALANCED" });
    expect(r.status).toBe(400);
    expect(errCode(r)).toBe("OUT_OF_REGION");
  });
});

describe("missing data display", () => {
  it("shows null as 'Data unavailable', never 0", () => {
    expect(fmtNumber(null, 0, "m")).toBe(UNAVAILABLE);
    expect(fmtSlope(null)).toBe(UNAVAILABLE);
    expect(fmtDistance(null)).toBe(UNAVAILABLE);
    expect(fmtText(null)).toBe(UNAVAILABLE);
    expect(fmtNumber(0, 0, "m")).toBe("0 m");
  });

  it("location in the data gap returns null elevation", () => {
    const r = handleMock("GET", "/regions/1/location?lon=77.66&lat=18.66");
    expect((r.body as { elevationM: number | null }).elevationM).toBeNull();
  });
});
