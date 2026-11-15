import { useLayers } from "@/api/queries";
import { useLayerData } from "@/components/explorer/use-layer-data";

// RedGrid layer keys (RedGrid API Contract); the hyphenated keys are those of the offline test fixtures.
const CONTEXT_LAYERS = new Set([
  "hazards",
  "science_targets",
  "safe_points",
  "science-targets",
  "safe-points",
]);

/** Context layers (hazards, science targets, safe points) shown on mission maps. */
export function useMissionMapLayers(regionId: number | undefined) {
  const layers = useLayers(regionId);
  return useLayerData(regionId, layers.data, (l) => CONTEXT_LAYERS.has(l.key)).vectorLayers;
}
