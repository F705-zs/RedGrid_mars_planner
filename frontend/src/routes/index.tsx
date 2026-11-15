import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Box, Map as MapIcon, RefreshCw, Settings2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { locationQuery, useLayers } from "@/api/queries";
import { ErrorState } from "@/components/common/states";
import { LayerPanel } from "@/components/explorer/LayerPanel";
import { LocationPanel } from "@/components/explorer/LocationPanel";
import { useLayerData } from "@/components/explorer/use-layer-data";
import { LazyMarsMap } from "@/components/map/LazyMarsMap";
import { Mars3DView } from "@/components/map/Mars3DView";
import type { ImageryStatus, RasterStatus } from "@/components/map/map-types";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { appendFootstep, loadFootsteps, saveFootsteps } from "@/lib/footsteps";
import { useRegionContext } from "@/lib/region-context";
import { cn } from "@/lib/utils";
import type { Layer, Position } from "@/types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Map Explorer — RedGrid" },
      {
        name: "description",
        content:
          "Explore Jezero Crater on Mars in 2D or 3D: toggle hazard, science and terrain layers and inspect any point.",
      },
      { property: "og:title", content: "Map Explorer — RedGrid" },
      {
        property: "og:description",
        content:
          "Layered Mars map of Jezero Crater with per-location terrain and environment details.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Explorer,
});

const HINT_KEY = "redgrid.explorerHintSeen";

function ImageryChip({
  status,
  grid,
  onRetry,
}: {
  status: ImageryStatus;
  grid: boolean;
  onRetry: () => void;
}) {
  const text =
    status.kind === "checking"
      ? "Imagery: checking…"
      : status.kind === "trek"
        ? "Imagery: NASA Mars Trek"
        : status.kind === "fallback"
          ? `Imagery: ${status.layerKey === "imagery_hirise" ? "HiRISE" : "CTX"} orthomosaic (backend)`
          : "Imagery unavailable";
  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-2 rounded-md border bg-panel/95 px-2 py-1 text-[11px]",
        status.kind === "none"
          ? "border-destructive/50 text-foreground"
          : "border-border text-muted-foreground",
      )}
      role={status.kind === "none" ? "alert" : undefined}
    >
      {text}
      {grid && (
        <span className="text-muted-foreground">· grid shown (coordinates only, not imagery)</span>
      )}
      {status.kind === "none" && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 text-sand hover:underline"
        >
          <RefreshCw className="size-3" /> Retry
        </button>
      )}
    </div>
  );
}

function Explorer() {
  const { region, isLoading: regionLoading, error: regionError, refetch } = useRegionContext();
  const layersQ = useLayers(region?.id);
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const [point, setPoint] = useState<Position | null>(null);
  const [layersCollapsed, setLayersCollapsed] = useState(false);
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [rasterStatus, setRasterStatus] = useState<Record<string, RasterStatus>>({});
  const [imagery, setImagery] = useState<ImageryStatus>({ kind: "checking" });
  const [imageryRetry, setImageryRetry] = useState(0);
  const [gridPref, setGridPref] = useState<boolean | null>(null);
  const [showCursor, setShowCursor] = useState(false);
  const [hint, setHint] = useState(false);
  const [footsteps, setFootsteps] = useState<Position[]>([]);

  useEffect(() => {
    setFootsteps(loadFootsteps());
    setHint(window.localStorage.getItem(HINT_KEY) !== "1");
  }, []);
  const dismissHint = () => {
    setHint(false);
    window.localStorage.setItem(HINT_KEY, "1");
  };

  // Grid: off when real imagery is shown, on by default only when no imagery is available; the user decides after.
  const showGrid = gridPref ?? imagery.kind === "none";

  const isOn = useCallback((l: Layer) => overrides[l.key] ?? l.defaultOn, [overrides]);
  const onRasterStatus = useCallback(
    (key: string, st: RasterStatus) =>
      setRasterStatus((s) => (s[key] === st ? s : { ...s, [key]: st })),
    [],
  );
  const { states, vectorLayers, rasterLayers } = useLayerData(
    region?.id,
    layersQ.data,
    isOn,
    rasterStatus,
  );

  const location = useQuery({
    ...locationQuery(region?.id ?? 0, point?.[0] ?? 0, point?.[1] ?? 0),
    enabled: !!region && !!point,
  });

  const onStep = useCallback((p: Position) => {
    setFootsteps((prev) => {
      const next = appendFootstep(prev, p);
      if (next !== prev) saveFootsteps(next);
      return next;
    });
  }, []);

  // V switches 2D / 3D (not while typing)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key.toLowerCase() !== "v" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      setView((v) => (v === "2d" ? "3d" : "2d"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (regionError)
    return <ErrorState error={regionError} onRetry={() => void refetch()} className="m-6" />;

  return (
    <div className="flex min-h-0 flex-1">
      <LayerPanel
        layers={layersQ.data}
        isLoading={regionLoading || layersQ.isLoading}
        error={layersQ.error}
        onRetry={() => layersQ.refetch()}
        states={states}
        onToggle={(key, on) => setOverrides((o) => ({ ...o, [key]: on }))}
        collapsed={layersCollapsed}
        onCollapsedChange={setLayersCollapsed}
      />

      <div className="relative min-w-0 flex-1">
        {region ? (
          <LazyMarsMap
            key={region.id}
            region={region}
            vectorLayers={vectorLayers}
            rasterLayers={rasterLayers}
            probe={point}
            onMapClick={(p) => {
              setPoint(p);
              if (hint) dismissHint();
            }}
            showGrid={showGrid}
            showCursor={showCursor}
            onRasterStatus={onRasterStatus}
            onImageryStatus={setImagery}
            imageryRetry={imageryRetry}
            footsteps={footsteps}
          />
        ) : (
          <div className="grid-backdrop h-full w-full animate-pulse bg-background" />
        )}

        <Mars3DView visible={view === "3d"} onStep={onStep} />

        {/* View switch and map options */}
        <div className="absolute left-3 top-3 z-[1100] flex items-center gap-1.5">
          <div
            className="flex overflow-hidden rounded-md border border-border bg-panel/95"
            role="group"
            aria-label="View"
          >
            {(["2d", "3d"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-pressed={view === v}
                title={`${v.toUpperCase()} view (V)`}
                className={cn(
                  "flex items-center gap-1 px-2 py-1 text-xs",
                  view === v
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v === "2d" ? <MapIcon className="size-3.5" /> : <Box className="size-3.5" />}
                {v.toUpperCase()}
              </button>
            ))}
          </div>
          {view === "2d" && (
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 bg-panel/95 px-2 text-xs"
                  aria-label="Map options"
                >
                  <Settings2 className="size-3.5" /> Map
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-64 space-y-2.5 text-sm">
                <label className="flex items-center justify-between gap-3">
                  Coordinate grid
                  <Switch checked={showGrid} onCheckedChange={setGridPref} />
                </label>
                <label className="flex items-center justify-between gap-3">
                  Cursor coordinates
                  <Switch checked={showCursor} onCheckedChange={setShowCursor} />
                </label>
                {footsteps.length > 1 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setFootsteps([]);
                      saveFootsteps([]);
                    }}
                  >
                    Clear footstep trail
                  </Button>
                )}
              </PopoverContent>
            </Popover>
          )}
        </div>

        {view === "2d" && (
          <div className="pointer-events-none absolute bottom-7 left-2 z-[1000] flex flex-col items-start gap-1">
            {footsteps.length > 1 && (
              <span className="rounded-md border border-border bg-panel/95 px-2 py-1 text-[11px] text-muted-foreground">
                Footsteps from the 3D walk (this session only, not saved)
              </span>
            )}
            <ImageryChip
              status={imagery}
              grid={showGrid}
              onRetry={() => setImageryRetry((n) => n + 1)}
            />
          </div>
        )}

        {view === "2d" && region && hint && !point && (
          <div className="absolute left-1/2 top-3 z-[1000] flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-panel/95 px-3 py-1 text-xs text-muted-foreground">
            Click the map to inspect a point · press V for 3D
            <button
              type="button"
              onClick={dismissHint}
              aria-label="Dismiss hint"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}
      </div>

      {point && view === "2d" && (
        <LocationPanel
          point={point}
          info={location.data}
          isLoading={location.isLoading}
          error={location.error}
          onClose={() => setPoint(null)}
        />
      )}
    </div>
  );
}
