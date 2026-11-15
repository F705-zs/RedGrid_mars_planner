// In-memory mock state. Built lazily (never at module scope) and reset on page reload.

import type { Annotation, Mission, Route } from "@/types";

import { PRESET_PRIORITIES } from "./data";
import { generateRoutes } from "./routes";

export interface MockDb {
  missions: Mission[];
  annotations: Annotation[];
  routes: Route[];
  seq: { mission: number; annotation: number; route: number };
}

let db: MockDb | null = null;

function seed(): MockDb {
  const d: MockDb = {
    missions: [],
    annotations: [],
    routes: [],
    seq: { mission: 0, annotation: 0, route: 0 },
  };
  const nextRoute = () => ++d.seq.route;

  const add = (
    m: Omit<
      Mission,
      "id" | "objective" | "priorityMix" | "reserveFraction" | "startIsBase" | "createdAt"
    >,
    notes: Omit<Annotation, "id" | "missionId">[],
    withRoutes: boolean,
  ) => {
    const mission: Mission = {
      objective: null,
      priorityMix: [],
      reserveFraction: 0.2,
      startIsBase: true,
      createdAt: "2026-11-01T00:00:00Z",
      ...m,
      id: ++d.seq.mission,
    };
    d.missions.push(mission);
    const anns = notes.map((a) => ({ ...a, id: ++d.seq.annotation, missionId: mission.id }));
    d.annotations.push(...anns);
    if (withRoutes) d.routes.push(...generateRoutes(mission, anns, nextRoute));
    return mission;
  };

  const planned = add(
    {
      regionId: 1,
      name: "Delta front traverse",
      startLon: 77.45,
      startLat: 18.44,
      destLon: 77.418,
      destLat: 18.496,
      profile: "BALANCED",
      priorities: PRESET_PRIORITIES.BALANCED,
      status: "PLANNED",
      selectedRouteId: null,
    },
    [
      {
        kind: "SCIENCE_STOP",
        lon: 77.436,
        lat: 18.47,
        note: "Sample layered outcrop",
        durationMin: 45,
        severity: null,
        radiusM: null,
      },
      {
        kind: "HAZARD_WARNING",
        lon: 77.405,
        lat: 18.468,
        note: "Boulders reported by rover",
        durationMin: null,
        severity: "MEDIUM",
        radiusM: 300,
      },
    ],
    true,
  );
  planned.selectedRouteId = d.routes.find(
    (r) => r.missionId === planned.id && r.routeType === "MISSION_PRIORITY",
  )!.id;

  add(
    {
      regionId: 1,
      name: "Crater floor survey",
      startLon: 77.392,
      startLat: 18.432,
      destLon: 77.512,
      destLat: 18.405,
      profile: "SAFETY_FOCUSED",
      priorities: PRESET_PRIORITIES.SAFETY_FOCUSED,
      status: "DRAFT",
      selectedRouteId: null,
    },
    [],
    false,
  );

  const finalized = add(
    {
      regionId: 1,
      name: "Carbonate margin sampling",
      startLon: 77.552,
      startLat: 18.482,
      destLon: 77.488,
      destLat: 18.43,
      profile: "SCIENCE_FOCUSED",
      priorities: PRESET_PRIORITIES.SCIENCE_FOCUSED,
      status: "FINALIZED",
      selectedRouteId: null,
    },
    [
      {
        kind: "SCIENCE_STOP",
        lon: 77.512,
        lat: 18.461,
        note: "Carbonate core",
        durationMin: 60,
        severity: null,
        radiusM: null,
      },
    ],
    true,
  );
  finalized.selectedRouteId = d.routes.find(
    (r) => r.missionId === finalized.id && r.routeType === "SAFEST",
  )!.id;

  return d;
}

export function getDb(): MockDb {
  db ??= seed();
  return db;
}

/** Test helper: start again from the seeded state. */
export function resetDb() {
  db = null;
}
