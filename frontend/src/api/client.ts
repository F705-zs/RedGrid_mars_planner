// The ONE module through which all RedGrid data flows (API Contract V6).
// Default: real HTTP calls to VITE_API_BASE_URL. If the API cannot be reached the call fails with NETWORK_ERROR;
// it never silently switches to mock data. VITE_USE_MOCKS=true (offline UI development only) answers from src/mocks.

import { API_BASE_URL, USE_MOCKS } from "@/config";
import type {
  Annotation,
  Category,
  CostModel,
  DemoWindow,
  PlanningConstant,
  PriorityPresetWeights,
  Providers,
  Resources,
  SetResourcesBody,
  TerrainClassMapping,
  TerrainGrid,
  ApiErrorBody,
  CreateAnnotationBody,
  CreateMissionBody,
  Dataset,
  FeatureCollection,
  Layer,
  LocationInfo,
  Mission,
  MissionStatus,
  PatchMissionBody,
  Priorities,
  PriorityPreset,
  Region,
  Report,
  Route,
  RouteProfile,
} from "@/types";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const isApiError = (e: unknown, code?: string): e is ApiError =>
  e instanceof ApiError && (code === undefined || e.code === code);

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

function toApiError(status: number, payload: unknown): ApiError {
  const err = (payload as ApiErrorBody | null)?.error;
  if (err && typeof err.code === "string")
    return new ApiError(err.code, err.message || "Request failed.", status, err.details ?? {});
  return new ApiError("INTERNAL_ERROR", `Request failed with status ${status}.`, status);
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (USE_MOCKS) {
    const { mockRequest } = await import("@/mocks/handlers");
    const res = await mockRequest(method, path, body);
    if (res.status >= 400) throw toApiError(res.status, res.body);
    return res.body as T;
  }

  let res: Response;
  try {
    const init: RequestInit = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json", Accept: "application/json" };
      init.body = JSON.stringify(body);
    }
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    if (typeof window !== "undefined" && window.location.hostname.endsWith("github.io")) {
      const { mockRequest } = await import("@/mocks/handlers");
      const mockRes = await mockRequest(method, path, body);
      if (mockRes.status >= 400) throw toApiError(mockRes.status, mockRes.body);
      return mockRes.body as T;
    }
    throw new ApiError("NETWORK_ERROR", `Could not reach the RedGrid API at ${API_BASE_URL}.`, 0);
  }
  if (res.status === 204) return undefined as T;
  const payload = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, payload);
  return payload as T;
}

/**
 * Create body for POST /missions. priorities and priorityMix are sent only for CUSTOM (API Contract V6: a preset must
 * not carry them); the server fills a preset's weights itself. Empty optional fields are left out so the backend's
 * defaults provider supplies them (shown as DEFAULT_ASSUMPTION).
 */
export function buildCreateMissionBody(
  input: Omit<CreateMissionBody, "priorities" | "priorityMix"> & {
    priorities: Priorities;
    priorityMix?: CreateMissionBody["priorityMix"];
  },
): CreateMissionBody {
  const { priorities, priorityMix, ...rest } = input;
  const body: CreateMissionBody = { ...rest };
  if (!body.objective) delete body.objective;
  if (body.resources && Object.keys(body.resources).length === 0) delete body.resources;
  if (rest.profile === ("CUSTOM" satisfies PriorityPreset)) {
    body.priorities = priorities;
    if (priorityMix && priorityMix.length) body.priorityMix = priorityMix;
  }
  return body;
}

export interface Bbox {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** URL of a RASTER layer rendered as a PNG for exactly this bbox (GET /regions/{id}/terrain/texture, V6). */
export function textureUrl(regionId: number, layerKey: string, bbox: Bbox, size: number): string {
  const p = new URLSearchParams({
    west: bbox.west.toFixed(6),
    south: bbox.south.toFixed(6),
    east: bbox.east.toFixed(6),
    north: bbox.north.toFixed(6),
    size: String(Math.round(Math.min(2048, Math.max(256, size)))),
    layer: layerKey,
  });
  return `${API_BASE_URL}/regions/${regionId}/terrain/texture?${p.toString()}`;
}

const q = (params: Record<string, string | number | undefined>) => {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && s.set(k, String(v)));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  getRegions: () => request<Region[]>("GET", "/regions"),
  getRegion: (regionId: number) => request<Region>("GET", `/regions/${regionId}`),
  getLayers: (regionId: number) => request<Layer[]>("GET", `/regions/${regionId}/layers`),
  getLayerGeojson: (regionId: number, key: string) =>
    request<FeatureCollection>(
      "GET",
      `/regions/${regionId}/layers/${encodeURIComponent(key)}/geojson`,
    ),
  getDatasets: (regionId: number) => request<Dataset[]>("GET", `/regions/${regionId}/datasets`),
  getRouteProfiles: () => request<RouteProfile[]>("GET", "/route-profiles"),
  getPriorityPresets: () => request<PriorityPresetWeights[]>("GET", "/priority-presets"),
  getCategories: () => request<Category[]>("GET", "/categories"),
  getTerrainClassMapping: () => request<TerrainClassMapping[]>("GET", "/terrain-class-mapping"),
  getCostModel: () => request<CostModel>("GET", "/cost-model"),
  getPlanningConstants: () => request<PlanningConstant[]>("GET", "/planning-constants"),
  getDemoWindow: () => request<DemoWindow | null>("GET", "/demo-window"),
  getProviders: () => request<Providers>("GET", "/providers"),
  getTerrain: (regionId: number, bbox: Bbox, maxSize = 256) =>
    request<TerrainGrid>("GET", `/regions/${regionId}/terrain${q({ ...bbox, maxSize })}`),
  getLocation: (regionId: number, lon: number, lat: number) =>
    request<LocationInfo>("GET", `/regions/${regionId}/location${q({ lon, lat })}`),

  createMission: (body: CreateMissionBody) => request<Mission>("POST", "/missions", body),
  getMissions: (status?: MissionStatus) => request<Mission[]>("GET", `/missions${q({ status })}`),
  getMission: (id: number) => request<Mission>("GET", `/missions/${id}`),
  patchMission: (id: number, body: PatchMissionBody) =>
    request<Mission>("PATCH", `/missions/${id}`, body),
  duplicateMission: (id: number) => request<Mission>("POST", `/missions/${id}/duplicate`),
  setMissionStatus: (id: number, status: MissionStatus) =>
    request<Mission>("PATCH", `/missions/${id}/status`, { status }),

  getAnnotations: (id: number) => request<Annotation[]>("GET", `/missions/${id}/annotations`),
  createAnnotation: (id: number, body: CreateAnnotationBody) =>
    request<Annotation>("POST", `/missions/${id}/annotations`, body),
  deleteAnnotation: (id: number, annotationId: number) =>
    request<void>("DELETE", `/missions/${id}/annotations/${annotationId}`),
  getResources: (id: number) => request<Resources>("GET", `/missions/${id}/resources`),
  setResources: (id: number, body: SetResourcesBody) =>
    request<Resources>("PUT", `/missions/${id}/resources`, body),

  calculateRoutes: (id: number) => request<Route[]>("POST", `/missions/${id}/routes`),
  getRoutes: (id: number) => request<Route[]>("GET", `/missions/${id}/routes`),
  recalculateRoutes: (id: number) => request<Route[]>("POST", `/missions/${id}/routes/recalculate`),
  selectRoute: (id: number, routeId: number) =>
    request<Mission>("PUT", `/missions/${id}/selected-route`, { routeId }),
  getReport: (id: number) => request<Report>("GET", `/missions/${id}/report`),
};
