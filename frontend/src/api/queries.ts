// React Query bindings for the API client. Data is fetched in the browser only
// (the API may be a local server or the in-memory mock), so pages render loading
// skeletons first and fill in after hydration.

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  CreateAnnotationBody,
  CreateMissionBody,
  MissionStatus,
  PatchMissionBody,
} from "@/types";

import { api } from "./client";

const STATIC = { staleTime: 5 * 60_000 };

export const keys = {
  regions: ["regions"] as const,
  region: (id: number) => ["regions", id] as const,
  layers: (regionId: number) => ["regions", regionId, "layers"] as const,
  geojson: (regionId: number, key: string) =>
    ["regions", regionId, "layers", key, "geojson"] as const,
  datasets: (regionId: number) => ["regions", regionId, "datasets"] as const,
  profiles: ["route-profiles"] as const,
  presets: ["priority-presets"] as const,
  constants: ["planning-constants"] as const,
  demoWindow: ["demo-window"] as const,
  providers: ["providers"] as const,
  resources: (id: number) => ["missions", id, "resources"] as const,
  location: (regionId: number, lon: number, lat: number) =>
    ["regions", regionId, "location", lon, lat] as const,
  missions: ["missions"] as const,
  missionList: (status?: MissionStatus) => ["missions", "list", status ?? "ALL"] as const,
  mission: (id: number) => ["missions", id] as const,
  annotations: (id: number) => ["missions", id, "annotations"] as const,
  routes: (id: number) => ["missions", id, "routes"] as const,
  report: (id: number) => ["missions", id, "report"] as const,
};

export const regionsQuery = () =>
  queryOptions({ queryKey: keys.regions, queryFn: api.getRegions, ...STATIC });
export const layersQuery = (regionId: number) =>
  queryOptions({
    queryKey: keys.layers(regionId),
    queryFn: () => api.getLayers(regionId),
    ...STATIC,
  });
export const geojsonQuery = (regionId: number, key: string) =>
  queryOptions({
    queryKey: keys.geojson(regionId, key),
    queryFn: () => api.getLayerGeojson(regionId, key),
    ...STATIC,
  });
export const datasetsQuery = (regionId: number) =>
  queryOptions({
    queryKey: keys.datasets(regionId),
    queryFn: () => api.getDatasets(regionId),
    ...STATIC,
  });
export const profilesQuery = () =>
  queryOptions({ queryKey: keys.profiles, queryFn: api.getRouteProfiles, ...STATIC });
export const presetsQuery = () =>
  queryOptions({ queryKey: keys.presets, queryFn: api.getPriorityPresets, ...STATIC });
export const constantsQuery = () =>
  queryOptions({ queryKey: keys.constants, queryFn: api.getPlanningConstants, ...STATIC });
export const demoWindowQuery = () =>
  queryOptions({ queryKey: keys.demoWindow, queryFn: api.getDemoWindow, ...STATIC });
export const providersQuery = () =>
  queryOptions({ queryKey: keys.providers, queryFn: api.getProviders, staleTime: 30_000 });
export const resourcesQuery = (id: number) =>
  queryOptions({ queryKey: keys.resources(id), queryFn: () => api.getResources(id) });
export const locationQuery = (regionId: number, lon: number, lat: number) =>
  queryOptions({
    queryKey: keys.location(regionId, lon, lat),
    queryFn: () => api.getLocation(regionId, lon, lat),
    staleTime: Infinity,
  });
export const missionsQuery = (status?: MissionStatus) =>
  queryOptions({ queryKey: keys.missionList(status), queryFn: () => api.getMissions(status) });
export const missionQuery = (id: number) =>
  queryOptions({ queryKey: keys.mission(id), queryFn: () => api.getMission(id) });
export const annotationsQuery = (id: number) =>
  queryOptions({ queryKey: keys.annotations(id), queryFn: () => api.getAnnotations(id) });
export const routesQuery = (id: number) =>
  queryOptions({ queryKey: keys.routes(id), queryFn: () => api.getRoutes(id) });
export const reportQuery = (id: number) =>
  queryOptions({
    queryKey: keys.report(id),
    queryFn: () => api.getReport(id),
    meta: { silentCodes: ["ROUTES_NOT_CALCULATED"] },
  });

export const useRegions = () => useQuery(regionsQuery());
export const useLayers = (regionId: number | undefined) =>
  useQuery({ ...layersQuery(regionId ?? 0), enabled: regionId !== undefined });
export const useDatasets = (regionId: number | undefined) =>
  useQuery({ ...datasetsQuery(regionId ?? 0), enabled: regionId !== undefined });
export const useRouteProfiles = () => useQuery(profilesQuery());
export const usePriorityPresets = () => useQuery(presetsQuery());
export const usePlanningConstants = () => useQuery(constantsQuery());
export const useDemoWindow = () => useQuery(demoWindowQuery());
export const useProviders = () => useQuery(providersQuery());
export const useResources = (id: number) => useQuery({ ...resourcesQuery(id), enabled: id > 0 });
export const useMissions = (status?: MissionStatus) => useQuery(missionsQuery(status));
export const useMission = (id: number) => useQuery(missionQuery(id));
export const useAnnotations = (id: number) => useQuery(annotationsQuery(id));
export const useRoutes = (id: number) => useQuery(routesQuery(id));
export const useReport = (id: number) => useQuery(reportQuery(id));

/* ---------- Mutations ---------- */

function useMissionInvalidation() {
  const qc = useQueryClient();
  return (id?: number) => {
    void qc.invalidateQueries({ queryKey: keys.missions });
    if (id !== undefined) void qc.invalidateQueries({ queryKey: keys.mission(id) });
  };
}

/** POST /missions then POST /missions/{id}/routes. */
export function useCreateMissionWithRoutes() {
  const invalidate = useMissionInvalidation();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      body,
      onStage,
    }: {
      body: CreateMissionBody;
      onStage?: (s: "creating" | "routing") => void;
    }) => {
      onStage?.("creating");
      const mission = await api.createMission(body);
      onStage?.("routing");
      try {
        const routes = await api.calculateRoutes(mission.id);
        qc.setQueryData(keys.routes(mission.id), routes);
        return { mission, routesError: null as unknown };
      } catch (routesError) {
        return { mission, routesError };
      }
    },
    onSuccess: ({ mission }) => invalidate(mission.id),
  });
}

export function usePatchMission(id: number) {
  const invalidate = useMissionInvalidation();
  return useMutation({
    mutationFn: (body: PatchMissionBody) => api.patchMission(id, body),
    onSuccess: () => invalidate(id),
  });
}

export function useDuplicateMission() {
  const invalidate = useMissionInvalidation();
  return useMutation({
    mutationFn: (id: number) => api.duplicateMission(id),
    onSuccess: () => invalidate(),
  });
}

export function useSetMissionStatus() {
  const invalidate = useMissionInvalidation();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: MissionStatus }) =>
      api.setMissionStatus(id, status),
    onSuccess: (m) => invalidate(m.id),
  });
}

export function useCreateAnnotation(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAnnotationBody) => api.createAnnotation(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.annotations(id) }),
  });
}

export function useDeleteAnnotation(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (annotationId: number) => api.deleteAnnotation(id, annotationId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.annotations(id) }),
  });
}

function useRoutesMutation(id: number, fn: (id: number) => Promise<import("@/types").Route[]>) {
  const qc = useQueryClient();
  const invalidate = useMissionInvalidation();
  return useMutation({
    mutationFn: () => fn(id),
    onSuccess: (routes) => {
      qc.setQueryData(keys.routes(id), routes);
      void qc.invalidateQueries({ queryKey: keys.report(id) });
      invalidate(id);
    },
  });
}

export const useCalculateRoutes = (id: number) => useRoutesMutation(id, api.calculateRoutes);
export const useRecalculateRoutes = (id: number) => useRoutesMutation(id, api.recalculateRoutes);

export function useSelectRoute(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (routeId: number) => api.selectRoute(id, routeId),
    onSuccess: (mission) => {
      qc.setQueryData(keys.mission(id), mission);
      void qc.invalidateQueries({ queryKey: keys.missions });
      void qc.invalidateQueries({ queryKey: keys.report(id) });
    },
  });
}
