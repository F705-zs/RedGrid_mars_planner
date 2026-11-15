// Mock implementation of the RedGrid REST API. Answers (method, path, body) with the same
// status codes and JSON shapes as the real API, mutating in-memory state.

import { inRegion } from "@/lib/geo";
import { canTransition } from "@/lib/mission-status";
import type {
  Annotation,
  ApiErrorBody,
  ApiErrorCode,
  CreateAnnotationBody,
  CreateMissionBody,
  Mission,
  MissionStatus,
  PatchMissionBody,
  Priorities,
  PriorityPreset,
  Region,
  Report,
  Severity,
} from "@/types";
import { MISSION_STATUSES, PRIORITY_KEYS, PRIORITY_PRESETS } from "@/types";

import {
  DATASETS,
  LAYER_FEATURES,
  LAYERS,
  MOCK_NOTICE,
  PRESET_PRIORITIES,
  REGIONS,
  PRESET_FIXTURES,
  ROUTE_PROFILES,
} from "./data";
import { getDb } from "./db";
import { generateRoutes } from "./routes";
import { locationInfo } from "./terrain";

export interface MockResponse {
  status: number;
  body: unknown;
}

class HttpError extends Error {
  constructor(
    public status: number,
    public code: ApiErrorCode,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const clone = <T>(v: T): T => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const ok = (body: unknown, status = 200): MockResponse => ({ status, body: clone(body) });

const STATUS: Partial<Record<ApiErrorCode, number>> = {
  VALIDATION_ERROR: 400,
  OUT_OF_REGION: 400,
  INVALID_PROFILE: 400,
  LAYER_NOT_VECTOR: 400,
  REGION_NOT_FOUND: 404,
  LAYER_NOT_FOUND: 404,
  MISSION_NOT_FOUND: 404,
  ROUTE_NOT_FOUND: 404,
  ANNOTATION_NOT_FOUND: 404,
  INVALID_STATUS_TRANSITION: 409,
  MISSION_FINALIZED: 409,
  ROUTE_NOT_IN_MISSION: 409,
  ROUTES_NOT_CALCULATED: 409,
};
const fail = (
  code: ApiErrorCode,
  message: string,
  details: Record<string, unknown> = {},
): never => {
  throw new HttpError(STATUS[code] ?? 500, code, message, details);
};

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function region(id: number): Region {
  return (
    REGIONS.find((r) => r.id === id) ??
    fail("REGION_NOT_FOUND", `Region ${id} was not found.`, { regionId: id })
  );
}
function mission(id: number): Mission {
  return (
    getDb().missions.find((m) => m.id === id) ??
    fail("MISSION_NOT_FOUND", `Mission ${id} was not found.`, { missionId: id })
  );
}
function editable(id: number): Mission {
  const m = mission(id);
  if (m.status === "FINALIZED")
    fail("MISSION_FINALIZED", "This mission is finalized and can no longer be changed.", {
      missionId: id,
    });
  return m;
}
function checkInRegion(r: Region, lon: number, lat: number, field: string) {
  if (!inRegion(r, lon, lat))
    fail("OUT_OF_REGION", `The ${field} point is outside ${r.name}.`, {
      field,
      lon,
      lat,
      regionId: r.id,
    });
}
function checkPriorities(v: unknown): Priorities {
  if (!v || typeof v !== "object")
    return fail("VALIDATION_ERROR", "Custom priorities are required.", { field: "priorities" });
  const p = v as Record<string, unknown>;
  for (const k of PRIORITY_KEYS)
    if (!isNum(p[k]) || (p[k] as number) < 0 || (p[k] as number) > 1)
      fail("VALIDATION_ERROR", `${k} must be a number between 0 and 1.`, {
        field: `priorities.${k}`,
      });
  const pr = Object.fromEntries(PRIORITY_KEYS.map((k) => [k, p[k]])) as unknown as Priorities;
  if (PRIORITY_KEYS.every((k) => pr[k] === 0))
    fail("VALIDATION_ERROR", "At least one priority weight must be above zero.", {
      field: "priorities",
    });
  return pr;
}

/** Validates create/patch fields and returns the resulting mission fields. */
function applyMissionFields(
  base: Partial<Mission>,
  body: PatchMissionBody,
  creating: boolean,
): Omit<Mission, "id" | "status" | "selectedRouteId"> {
  const merged = { ...base, ...body } as Partial<CreateMissionBody> & Partial<Mission>;
  if (!isNum(merged.regionId))
    fail("VALIDATION_ERROR", "regionId is required.", { field: "regionId" });
  const r = region(merged.regionId!);
  const name = typeof merged.name === "string" ? merged.name.trim() : "";
  if (!name) fail("VALIDATION_ERROR", "Mission name is required.", { field: "name" });
  if (name.length > 120)
    fail("VALIDATION_ERROR", "Mission name must be 120 characters or fewer.", { field: "name" });
  for (const f of ["startLon", "startLat", "destLon", "destLat"] as const)
    if (!isNum(merged[f])) fail("VALIDATION_ERROR", `${f} must be a number.`, { field: f });
  checkInRegion(r, merged.startLon!, merged.startLat!, "start");
  checkInRegion(r, merged.destLon!, merged.destLat!, "destination");
  if (merged.startLon === merged.destLon && merged.startLat === merged.destLat)
    fail("VALIDATION_ERROR", "Start and destination must be different points.", {
      field: "destLon",
    });
  const profile = merged.profile as PriorityPreset;
  if (!PRIORITY_PRESETS.includes(profile))
    fail("INVALID_PROFILE", `Unknown profile "${String(profile)}".`, { field: "profile" });
  let priorities: Priorities;
  if (profile === "CUSTOM")
    priorities = checkPriorities(body.priorities ?? (creating ? undefined : base.priorities));
  else priorities = PRESET_PRIORITIES[profile as Exclude<PriorityPreset, "CUSTOM">];
  return {
    regionId: r.id,
    name,
    objective:
      typeof merged.objective === "string" && merged.objective.trim()
        ? merged.objective.trim()
        : null,
    startLon: merged.startLon!,
    startLat: merged.startLat!,
    destLon: merged.destLon!,
    destLat: merged.destLat!,
    profile,
    priorities: { ...priorities },
    priorityMix: profile === "CUSTOM" ? (body.priorityMix ?? base.priorityMix ?? []) : [],
    reserveFraction: isNum(merged.reserveFraction)
      ? merged.reserveFraction!
      : (base.reserveFraction ?? 0.2),
    startIsBase:
      typeof merged.startIsBase === "boolean" ? merged.startIsBase : (base.startIsBase ?? true),
    createdAt: base.createdAt ?? "2026-11-01T00:00:00Z",
  };
}

function calculateRoutes(m: Mission) {
  const d = getDb();
  d.routes = d.routes.filter((r) => r.missionId !== m.id);
  const routes = generateRoutes(
    m,
    d.annotations.filter((a) => a.missionId === m.id),
    () => ++d.seq.route,
  );
  d.routes.push(...routes);
  m.selectedRouteId = null;
  return routes;
}

function validateAnnotation(
  m: Mission,
  b: Partial<CreateAnnotationBody>,
): Omit<Annotation, "id" | "missionId"> {
  if (b.kind !== "SCIENCE_STOP" && b.kind !== "HAZARD_WARNING")
    fail("VALIDATION_ERROR", "kind must be SCIENCE_STOP or HAZARD_WARNING.", { field: "kind" });
  if (!isNum(b.lon) || !isNum(b.lat))
    fail("VALIDATION_ERROR", "lon and lat must be numbers.", { field: "lon" });
  checkInRegion(region(m.regionId), b.lon!, b.lat!, "annotation");
  const note = typeof b.note === "string" ? b.note.trim() : "";
  if (note.length > 500)
    fail("VALIDATION_ERROR", "Note must be 500 characters or fewer.", { field: "note" });
  if (b.kind === "SCIENCE_STOP") {
    if (!isNum(b.durationMin) || b.durationMin! < 1 || b.durationMin! > 600)
      fail("VALIDATION_ERROR", "durationMin must be between 1 and 600.", { field: "durationMin" });
    return {
      kind: b.kind,
      lon: b.lon!,
      lat: b.lat!,
      note,
      durationMin: Math.round(b.durationMin!),
      severity: null,
      radiusM: null,
    };
  }
  if (!(["LOW", "MEDIUM", "HIGH"] as Severity[]).includes(b.severity as Severity))
    fail("VALIDATION_ERROR", "severity must be LOW, MEDIUM or HIGH.", { field: "severity" });
  if (!isNum(b.radiusM) || b.radiusM! < 10 || b.radiusM! > 5_000)
    fail("VALIDATION_ERROR", "radiusM must be between 10 and 5000.", { field: "radiusM" });
  return {
    kind: "HAZARD_WARNING",
    lon: b.lon!,
    lat: b.lat!,
    note,
    durationMin: null,
    severity: b.severity!,
    radiusM: Math.round(b.radiusM!),
  };
}

type Handler = (params: [number, number], query: URLSearchParams, body: any) => MockResponse; // eslint-disable-line @typescript-eslint/no-explicit-any
const routes: [string, RegExp, Handler][] = [];
const on = (method: string, pattern: string, h: Handler) =>
  routes.push([
    method,
    new RegExp("^" + pattern.replace(/:(\w+)/g, "(-?\\d+)").replace(/\{key\}/g, "([\\w-]+)") + "$"),
    h,
  ]);

on("GET", "/regions", () => ok(REGIONS));
on("GET", "/regions/:id", ([id]) => ok(region(id)));
on("GET", "/regions/:id/layers", ([id]) => ok(LAYERS.filter((l) => l.regionId === region(id).id)));
on("GET", "/regions/:id/datasets", ([id]) => {
  region(id);
  return ok(DATASETS);
});
on("GET", "/route-profiles", () => ok(ROUTE_PROFILES));
on("GET", "/priority-presets", () => ok(PRESET_FIXTURES));
on("GET", "/planning-constants", () => ok([]));
on("GET", "/demo-window", () => ok(null));
on("GET", "/regions/:id/location", ([id], q) => {
  const r = region(id);
  const lon = Number(q.get("lon"));
  const lat = Number(q.get("lat"));
  if (!q.get("lon") || !q.get("lat") || !Number.isFinite(lon) || !Number.isFinite(lat))
    fail("VALIDATION_ERROR", "lon and lat query parameters are required numbers.", {
      field: "lon",
    });
  checkInRegion(r, lon, lat, "selected");
  return ok(locationInfo(r, lon, lat));
});

on("POST", "/missions", (_, __, body: CreateMissionBody) => {
  const d = getDb();
  const fields = applyMissionFields({}, body ?? {}, true);
  const m: Mission = { id: ++d.seq.mission, ...fields, status: "DRAFT", selectedRouteId: null };
  d.missions.push(m);
  return ok(m, 201);
});
on("GET", "/missions", (_, q) => {
  const status = q.get("status");
  if (status && !MISSION_STATUSES.includes(status as MissionStatus))
    fail("VALIDATION_ERROR", `Unknown status "${status}".`, { field: "status" });
  return ok(getDb().missions.filter((m) => !status || m.status === status));
});
on("GET", "/missions/:id", ([id]) => ok(mission(id)));
on("PATCH", "/missions/:id", ([id], _, body: PatchMissionBody) => {
  const m = editable(id);
  Object.assign(m, applyMissionFields(m, body ?? {}, false));
  return ok(m);
});
on("POST", "/missions/:id/duplicate", ([id]) => {
  const d = getDb();
  const src = mission(id);
  const copy: Mission = {
    ...clone(src),
    id: ++d.seq.mission,
    name: `${src.name} (copy)`,
    status: "DRAFT",
    selectedRouteId: null,
  };
  d.missions.push(copy);
  d.annotations
    .filter((a) => a.missionId === src.id)
    .forEach((a) => d.annotations.push({ ...a, id: ++d.seq.annotation, missionId: copy.id }));
  return ok(copy, 201);
});
on("PATCH", "/missions/:id/status", ([id], _, body: { status?: MissionStatus }) => {
  const m = mission(id);
  const to = body?.status;
  if (!to || !MISSION_STATUSES.includes(to))
    fail("VALIDATION_ERROR", "status must be DRAFT, PLANNED or FINALIZED.", { field: "status" });
  if (!canTransition(m.status, to!))
    fail("INVALID_STATUS_TRANSITION", `A ${m.status} mission cannot change to ${to}.`, {
      from: m.status,
      to,
    });
  m.status = to!;
  return ok(m);
});

on("GET", "/missions/:id/annotations", ([id]) =>
  ok(getDb().annotations.filter((a) => a.missionId === mission(id).id)),
);
on("POST", "/missions/:id/annotations", ([id], _, body: CreateAnnotationBody) => {
  const d = getDb();
  const m = editable(id);
  const a: Annotation = {
    id: ++d.seq.annotation,
    missionId: m.id,
    ...validateAnnotation(m, body ?? {}),
  };
  d.annotations.push(a);
  return ok(a, 201);
});
on("DELETE", "/missions/:id/annotations/:aid", ([id, aid]) => {
  const d = getDb();
  editable(id);
  const i = d.annotations.findIndex((a) => a.id === aid && a.missionId === id);
  if (i < 0)
    fail("ANNOTATION_NOT_FOUND", `Annotation ${aid} was not found.`, { annotationId: aid });
  d.annotations.splice(i, 1);
  return { status: 204, body: null };
});

on("POST", "/missions/:id/routes", ([id]) => ok(calculateRoutes(editable(id)), 201));
on("GET", "/missions/:id/routes", ([id]) =>
  ok(getDb().routes.filter((r) => r.missionId === mission(id).id)),
);
on("POST", "/missions/:id/routes/recalculate", ([id]) => ok(calculateRoutes(editable(id))));
on("PUT", "/missions/:id/selected-route", ([id], _, body: { routeId?: number }) => {
  const m = editable(id);
  if (!isNum(body?.routeId)) fail("VALIDATION_ERROR", "routeId is required.", { field: "routeId" });
  const route = getDb().routes.find((r) => r.id === body.routeId);
  if (!route)
    fail("ROUTE_NOT_FOUND", `Route ${body.routeId} was not found.`, { routeId: body.routeId });
  if (route!.missionId !== m.id)
    fail("ROUTE_NOT_IN_MISSION", "That route belongs to a different mission.", {
      routeId: body.routeId,
    });
  m.selectedRouteId = route!.id;
  return ok(m);
});
on("GET", "/missions/:id/report", ([id]) => {
  const d = getDb();
  const m = mission(id);
  const rs = d.routes.filter((r) => r.missionId === m.id);
  if (rs.length === 0)
    fail("ROUTES_NOT_CALCULATED", "Routes have not been calculated for this mission yet.", {
      missionId: id,
    });
  const recommendedRoute =
    rs.find((r) => r.id === m.selectedRouteId) ??
    [...rs].filter((r) => r.feasible).sort((a, b) => b.missionMatch - a.missionMatch)[0] ??
    null;
  const fixtureValue = (value: number, unit: string) => ({
    value,
    unit,
    source: "DEFAULT_ASSUMPTION" as const,
    observedAt: null,
    dataState: "DEMONSTRATION_DATA" as const,
  });
  const report: Report = {
    mission: m,
    routes: rs,
    recommendedRoute,
    annotations: d.annotations.filter((a) => a.missionId === m.id),
    sources: DATASETS,
    costModel: {
      id: 1,
      version: 0,
      method: "HAND_SET",
      status: "ACTIVE",
      trainedOn: null,
      trainingSummary: "Test fixture",
      testScore: null,
      createdAt: "2026-11-01T00:00:00Z",
    },
    trainingSources: [],
    providersUsed: [
      {
        name: "test-fixture",
        kind: "ALGORITHM",
        transport: "LOCAL",
        version: "fixture",
        status: "READY",
      },
    ],
    constants: [],
    terrainClassMapping: [],
    demoWindow: null,
    resources: {
      missionId: m.id,
      oxygenKg: fixtureValue(0.6, "kg"),
      batteryWh: fixtureValue(800, "Wh"),
      metabolicRateW: fixtureValue(300, "W"),
      suitPowerW: fixtureValue(90, "W"),
      reserveFraction: m.reserveFraction,
      startIsBase: m.startIsBase,
      usableOxygenKg: 0.6 * (1 - m.reserveFraction),
      usableBatteryWh: 800 * (1 - m.reserveFraction),
      providers: [],
    },
    caveats: ["Test fixtures: no value in this report is a real result."],
    notice: MOCK_NOTICE,
  };
  return ok(report);
});

// Layer GeoJSON: key is a string segment.
const GEOJSON = /^\/regions\/(-?\d+)\/layers\/([\w-]+)\/geojson$/;

function errorBody(e: HttpError): ApiErrorBody {
  return { error: { code: e.code, message: e.message, details: e.details } };
}

/** Synchronous core, used directly by tests. */
export function handleMock(method: string, url: string, body?: unknown): MockResponse {
  const [rawPath, qs = ""] = url.split("?");
  const path = rawPath ?? "";
  const query = new URLSearchParams(qs);
  try {
    const g = GEOJSON.exec(path);
    if (method === "GET" && g) {
      const r = region(Number(g[1]!));
      const layer = LAYERS.find((l) => l.regionId === r.id && l.key === g[2]!);
      if (!layer) fail("LAYER_NOT_FOUND", `Layer "${g[2]!}" was not found.`, { key: g[2]! });
      if (layer!.kind !== "VECTOR")
        fail("LAYER_NOT_VECTOR", `Layer "${g[2]!}" is a raster layer.`, { key: g[2]! });
      return ok(LAYER_FEATURES[layer!.key] ?? { type: "FeatureCollection", features: [] });
    }
    for (const [m, re, h] of routes) {
      if (m !== method) continue;
      const match = re.exec(path);
      if (match) return h(match.slice(1).map(Number) as [number, number], query, body);
    }
    return {
      status: 404,
      body: {
        error: { code: "NOT_FOUND", message: `No endpoint for ${method} ${path}.`, details: {} },
      },
    };
  } catch (e) {
    if (e instanceof HttpError) return { status: e.status, body: errorBody(e) };
    console.error(e);
    return {
      status: 500,
      body: {
        error: { code: "INTERNAL_ERROR", message: "Unexpected mock server error.", details: {} },
      },
    };
  }
}

const SLOW = /\/routes(\/recalculate)?$/;

/** Async wrapper with a short simulated network delay so loading states are visible. */
export async function mockRequest(
  method: string,
  url: string,
  body?: unknown,
): Promise<MockResponse> {
  const delay =
    method !== "GET" && SLOW.test(url.split("?")[0] ?? "") ? 1_100 : method === "GET" ? 250 : 350;
  await new Promise((r) => setTimeout(r, delay));
  return handleMock(method, url, body === undefined ? undefined : clone(body));
}
