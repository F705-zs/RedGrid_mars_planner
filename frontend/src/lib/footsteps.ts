// Temporary astronaut footsteps from the 3D walk, drawn on the 2D map.
// kept for the browser session only (sessionStorage); never sent to the backend or saved with a mission.

import type { Position } from "@/types";

/** The 3D scene's origin (landing site) and the Mars 2000 sphere radius used by the terrain products. */
export const SCENE_ORIGIN = { lon: 77.45088573, lat: 18.44462715 };
const R_MARS = 3_396_190;
const KEY = "redgrid.footsteps";
/** Minimum ground distance between two stored footstep points. */
export const FOOTSTEP_SPACING_M = 2;

/** 3D scene frame (x = metres east, z = metres SOUTH of the landing site) → [lon, lat]. */
export function sceneToLonLat(eastM: number, northM: number): Position {
  const lat0 = (SCENE_ORIGIN.lat * Math.PI) / 180;
  const lon = SCENE_ORIGIN.lon + ((eastM / (R_MARS * Math.cos(lat0))) * 180) / Math.PI;
  const lat = SCENE_ORIGIN.lat + ((northM / R_MARS) * 180) / Math.PI;
  return [Math.round(lon * 1e8) / 1e8, Math.round(lat * 1e8) / 1e8];
}

export function loadFootsteps(): Position[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(window.sessionStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? (v as Position[]) : [];
  } catch {
    return [];
  }
}

export function saveFootsteps(points: Position[]): void {
  try {
    if (points.length) window.sessionStorage.setItem(KEY, JSON.stringify(points));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* storage full or blocked: the trail simply is not kept */
  }
}

/** Appends a point if it is at least FOOTSTEP_SPACING_M from the last one (local planar distance). */
export function appendFootstep(points: Position[], p: Position): Position[] {
  const last = points[points.length - 1];
  if (last) {
    const kx = (R_MARS * Math.cos((p[1] * Math.PI) / 180) * Math.PI) / 180;
    const ky = (R_MARS * Math.PI) / 180;
    if (Math.hypot((p[0] - last[0]) * kx, (p[1] - last[1]) * ky) < FOOTSTEP_SPACING_M)
      return points;
  }
  return [...points, p];
}
