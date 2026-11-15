import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";

import { geojsonQuery } from "@/api/queries";
import type { MapRasterLayer, MapVectorLayer, RasterStatus } from "@/components/map/map-types";
import type { Layer } from "@/types";

import type { LayerRowState } from "./LayerPanel";

/**
 * Fetches GeoJSON for the switched-on VECTOR layers. Switched-on RASTER layers are drawn by the map from the
 * backend texture endpoint (RedGrid); their load status comes back through rasterStatus.
 */
export function useLayerData(
  regionId: number | undefined,
  layers: Layer[] | undefined,
  isOn: (l: Layer) => boolean,
  rasterStatus: Record<string, RasterStatus> = {},
) {
  const onVector = (layers ?? []).filter((l) => l.kind === "VECTOR" && isOn(l));
  const results = useQueries({
    queries: onVector.map((l) => ({
      ...geojsonQuery(regionId ?? 0, l.key),
      enabled: regionId !== undefined,
    })),
  });

  return useMemo(() => {
    const states: Record<string, LayerRowState> = {};
    const vectorLayers: MapVectorLayer[] = [];
    const rasterLayers: MapRasterLayer[] = [];
    for (const l of layers ?? []) {
      const on = isOn(l);
      states[l.key] = { on };
      if (!on) continue;
      if (l.kind === "RASTER") {
        rasterLayers.push({ key: l.key });
        const st = rasterStatus[l.key];
        states[l.key] = { on, loading: st === "loading", rasterUnavailable: st === "unavailable" };
      }
    }
    onVector.forEach((l, i) => {
      const r = results[i];
      states[l.key] = { on: true, loading: r?.isLoading, error: r?.error, data: r?.data };
      if (r?.data) vectorLayers.push({ key: l.key, data: r.data });
    });
    return { states, vectorLayers, rasterLayers };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers, results, rasterStatus, onVector.map((l) => l.key).join(",")]);
}
