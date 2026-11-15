// Geographic helpers. The API and GeoJSON use [lon, lat]; Leaflet (EPSG:4326) wants
// [lat, lon]. toLatLng is the ONE place that conversion happens.

import type { Position, Region } from "@/types";

export const MARS_RADIUS_M = 3_389_500;

export type LatLngTuple = [lat: number, lon: number];

/** [lon, lat] (API / GeoJSON) → [lat, lon] (Leaflet). */
export function toLatLng(position: Position): LatLngTuple {
  return [position[1], position[0]];
}

/** Leaflet lat/lng → [lon, lat] for the API, rounded to ~1 cm. */
export function fromLatLng(lat: number, lng: number): Position {
  return [round6(lng), round6(lat)];
}

export const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Great-circle distance on Mars in metres. */
export function distanceM(a: Position, b: Position): number {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * MARS_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineLengthM(coords: Position[]): number {
  let total = 0;
  for (let i = 1; i < coords.length; i++) total += distanceM(coords[i - 1]!, coords[i]!);
  return total;
}

/** Point offset by east/north metres (small-distance approximation). */
export function offsetM(p: Position, eastM: number, northM: number): Position {
  const lat = p[1] + deg(northM / MARS_RADIUS_M);
  const lon = p[0] + deg(eastM / (MARS_RADIUS_M * Math.cos(rad(p[1]))));
  return [lon, lat];
}

/** Polygon ring approximating a circle of radiusM on Mars (Leaflet's L.Circle assumes Earth). */
export function circleRing(center: Position, radiusM: number, steps = 48): Position[] {
  const ring: Position[] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push(offsetM(center, Math.cos(a) * radiusM, Math.sin(a) * radiusM));
  }
  return ring;
}

/** Shortest distance from p to a polyline, in metres (local planar approximation). */
export function distanceToLineM(p: Position, line: Position[]): number {
  if (line.length === 1) return distanceM(p, line[0]!);
  const kx = MARS_RADIUS_M * Math.cos(rad(p[1])) * (Math.PI / 180);
  const ky = MARS_RADIUS_M * (Math.PI / 180);
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const [a0, a1] = line[i - 1]!;
    const [b0, b1] = line[i]!;
    const ax = (a0 - p[0]) * kx;
    const ay = (a1 - p[1]) * ky;
    const bx = (b0 - p[0]) * kx;
    const by = (b1 - p[1]) * ky;
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2));
    best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy));
  }
  return best;
}

export function pointInRing(p: Position, ring: Position[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]!;
    const [xj, yj] = ring[j]!;
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

export function inRegion(region: Region, lon: number, lat: number): boolean {
  return (
    lon >= region.bboxWest &&
    lon <= region.bboxEast &&
    lat >= region.bboxSouth &&
    lat <= region.bboxNorth
  );
}

/** Formats a lon/lat pair for display, east-positive. */
export function formatLonLat(lon: number, lat: number, digits = 4): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(digits)}°${ns} ${Math.abs(lon).toFixed(digits)}°${ew}`;
}
