import { ChevronDown, ChevronsLeft, Info, Layers, Loader2 } from "lucide-react";
import { useState } from "react";

import { DataStateBadge } from "@/components/common/badges";
import { ErrorState } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FEATURE_TYPE_LABEL } from "@/lib/labels";
import { GROUP_ORDER, layerGroup } from "@/lib/layer-groups";
import { cn } from "@/lib/utils";
import type { FeatureCollection, FeatureType, Layer } from "@/types";

import { FeatureSwatch } from "./FeatureSwatch";

export interface LayerRowState {
  on: boolean;
  loading?: boolean | undefined;
  error?: unknown;
  data?: FeatureCollection | undefined;
  rasterUnavailable?: boolean | undefined;
}

function featureCounts(data?: FeatureCollection): [FeatureType, number][] {
  const m = new Map<FeatureType, number>();
  data?.features.forEach((f) =>
    m.set(f.properties.featureType, (m.get(f.properties.featureType) ?? 0) + 1),
  );
  return [...m.entries()];
}

function LayerRow({
  layer,
  state,
  onToggle,
}: {
  layer: Layer;
  state: LayerRowState;
  onToggle: (on: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const id = `layer-${layer.key}`;
  const counts = featureCounts(state.data);
  return (
    <li className="px-3 py-1.5">
      <div className="flex items-center gap-2.5">
        <Switch
          id={id}
          checked={state.on}
          onCheckedChange={onToggle}
          aria-describedby={`${id}-ds`}
          className="scale-90"
        />
        <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer truncate text-sm">
          {layer.displayName}
        </label>
        {state.loading && (
          <Loader2
            className="size-3.5 animate-spin text-muted-foreground"
            aria-label="Loading layer"
          />
        )}
        {state.on && state.rasterUnavailable && (
          <span
            className="text-[11px] text-muted-foreground"
            title="The backend has no prepared data for this layer here."
          >
            Unavailable
          </span>
        )}
        {state.on && layer.kind === "VECTOR" && !!state.error && (
          <span className="text-[11px] text-destructive">Error</span>
        )}
        {/* Swatches double as the legend: the colours are the map's own */}
        {state.on && counts.length > 0 && !open && (
          <span className="flex items-center gap-1" aria-hidden>
            {counts.map(([t]) => (
              <FeatureSwatch key={t} type={t} />
            ))}
          </span>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="rounded p-0.5 text-muted-foreground hover:text-foreground"
              aria-label={`${layer.displayName}: details`}
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? <ChevronDown className="size-3.5" /> : <Info className="size-3.5" />}
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" className="max-w-64">
            <p className="font-medium">{layer.dataset.name}</p>
            <p className="text-muted-foreground">{layer.dataset.provider}</p>
          </TooltipContent>
        </Tooltip>
      </div>
      <span id={`${id}-ds`} className="sr-only">
        Dataset: {layer.dataset.name}. Data state: {layer.dataState}.
      </span>
      {open && (
        <div className="mt-1.5 space-y-1.5 rounded-md bg-surface/50 px-2.5 py-2 text-xs">
          <DataStateBadge state={layer.dataState} />
          <p className="text-muted-foreground">
            {layer.dataset.name} · {layer.dataset.provider}
          </p>
          {state.on && layer.kind === "VECTOR" && state.data && (
            <ul className="space-y-1">
              {counts.map(([t, n]) => (
                <li key={t} className="flex items-center gap-2 text-muted-foreground">
                  <FeatureSwatch type={t} />
                  {FEATURE_TYPE_LABEL[t]}
                  <span className="data-value ml-auto">{n}</span>
                </li>
              ))}
              {state.data.features.length === 0 && (
                <li className="text-muted-foreground">No features in this region.</li>
              )}
            </ul>
          )}
          {state.on && layer.kind === "VECTOR" && !!state.error && (
            <p className="text-destructive">Could not load this layer.</p>
          )}
        </div>
      )}
    </li>
  );
}

export function LayerPanel({
  layers,
  isLoading,
  error,
  onRetry,
  states,
  onToggle,
  collapsed,
  onCollapsedChange,
}: {
  layers: Layer[] | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  states: Record<string, LayerRowState>;
  onToggle: (key: string, on: boolean) => void;
  collapsed: boolean;
  onCollapsedChange: (c: boolean) => void;
}) {
  if (collapsed)
    return (
      <aside
        className="flex w-10 shrink-0 flex-col items-center border-r border-border bg-panel py-2"
        aria-label="Layers (collapsed)"
      >
        <button
          type="button"
          onClick={() => onCollapsedChange(false)}
          className="rounded p-1.5 text-muted-foreground hover:bg-surface hover:text-foreground"
          aria-label="Show layers"
          title="Show layers"
        >
          <Layers className="size-4" />
        </button>
      </aside>
    );
  const groups = GROUP_ORDER.map((g) => ({
    g,
    list: (layers ?? []).filter((l) => layerGroup(l) === g),
  })).filter((x) => x.list.length);
  return (
    <aside
      className="flex w-72 shrink-0 flex-col border-r border-border bg-panel"
      aria-label="Layers"
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <h2 className="flex-1 text-sm font-semibold">Layers</h2>
        <button
          type="button"
          onClick={() => onCollapsedChange(true)}
          className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"
          aria-label="Collapse layers"
          title="Collapse"
        >
          <ChevronsLeft className="size-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {isLoading ? (
          <div className="space-y-3 p-3">
            {Array.from({ length: 7 }, (_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-4 w-8 rounded-full" />
                <Skeleton className="h-4 flex-1" />
              </div>
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={onRetry} className="m-3 py-8" />
        ) : !layers?.length ? (
          <p className="p-3 text-sm text-muted-foreground">No layers available for this region.</p>
        ) : (
          groups.map(({ g, list }) => (
            <section key={g} className={cn("pb-1")}>
              <h3 className="eyebrow px-3 pb-0.5 pt-2">{g}</h3>
              <ul>
                {list.map((l) => (
                  <LayerRow
                    key={l.key}
                    layer={l}
                    state={states[l.key] ?? { on: false }}
                    onToggle={(on) => onToggle(l.key, on)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </aside>
  );
}
