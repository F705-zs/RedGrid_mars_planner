import type { Layer } from "@/types";

/**
 * User-oriented group for a layer, derived from its key (no fixed list: any layer the API adds is placed by the same
 * rules, and anything unmatched lands in Terrain).
 */
export function layerGroup(layer: Layer): string {
  const k = layer.key.toLowerCase();
  if (k.startsWith("imagery")) return "Imagery";
  if (/hazard|rim|scarp/.test(k)) return "Hazards";
  if (/science/.test(k)) return "Science";
  if (/thermal|comm_coverage|weather|dust|environment/.test(k)) return "Environment";
  if (/safe|comm|rover|landing|base|ellipse/.test(k)) return "Mission context";
  return "Terrain";
}
export const GROUP_ORDER = [
  "Imagery",
  "Terrain",
  "Environment",
  "Hazards",
  "Science",
  "Mission context",
];
