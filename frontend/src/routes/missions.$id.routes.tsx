import { createFileRoute, Link } from "@tanstack/react-router";
import { GitCompareArrows, Loader2, Route as RouteIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { useAnnotations, useCalculateRoutes, useRoutes, useSelectRoute } from "@/api/queries";
import { EmptyState, ErrorState, PanelSkeleton } from "@/components/common/states";
import { LazyMarsMap } from "@/components/map/LazyMarsMap";
import { FinalizedBanner } from "@/components/mission/FinalizedBanner";
import { MissionHeader } from "@/components/mission/MissionHeader";
import { RouteCard, RouteSwatch } from "@/components/mission/RouteCard";
import { RouteRadar } from "@/components/mission/RouteRadar";
import { useMissionMapLayers } from "@/components/mission/use-mission-map-layers";
import { useMissionPage } from "@/components/mission/use-mission-page";
import { Button } from "@/components/ui/button";
import { ROUTE_TYPE_LABEL } from "@/lib/labels";
import type { Position } from "@/types";
import { ROUTE_TYPES } from "@/types";

export const Route = createFileRoute("/missions/$id/routes")({
  head: () => ({
    meta: [
      { title: "Route Comparison — RedGrid" },
      {
        name: "description",
        content:
          "Compare four Mars walking routes by risk, feasibility, distance, slope, hazards and science value.",
      },
      { property: "og:title", content: "Route Comparison — RedGrid" },
      {
        property: "og:description",
        content: "Side-by-side comparison of route alternatives for a Mars mission.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: RouteComparison,
});

function RouteComparison() {
  const { id: idParam } = Route.useParams();
  const { id, mission, region, finalized } = useMissionPage(idParam);
  const routes = useRoutes(id);
  const annotations = useAnnotations(id);
  const calculate = useCalculateRoutes(id);
  const select = useSelectRoute(id);
  const contextLayers = useMissionMapLayers(region?.id);
  const [hovered, setHovered] = useState<number | null>(null);

  const sorted = useMemo(
    () =>
      [...(routes.data ?? [])].sort(
        (a, b) => ROUTE_TYPES.indexOf(a.routeType) - ROUTE_TYPES.indexOf(b.routeType),
      ),
    [routes.data],
  );
  const m = mission.data;
  const endpoints = m
    ? [
        { kind: "start" as const, position: [m.startLon, m.startLat] as Position },
        { kind: "destination" as const, position: [m.destLon, m.destLat] as Position },
      ]
    : [];
  const fitTo = useMemo(
    () =>
      m
        ? ([
            [m.startLon, m.startLat],
            [m.destLon, m.destLat],
          ] as Position[])
        : undefined,
    // Refit only when the mission changes, not on every data refresh (original intent)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [m?.id],
  );

  if (mission.error) return <ErrorState error={mission.error} className="m-6" />;

  const computing = calculate.isPending;
  const busy = select.isPending || computing;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MissionHeader id={id} mission={m} />
      {finalized && <FinalizedBanner />}
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {region && m ? (
            <LazyMarsMap
              key={region.id}
              region={region}
              vectorLayers={contextLayers}
              annotations={annotations.data ?? []}
              endpoints={endpoints}
              fitTo={fitTo}
              routes={sorted.map((r) => ({
                route: r,
                highlighted: hovered === r.id || (hovered === null && r.id === m.selectedRouteId),
                dimmed: hovered !== null && hovered !== r.id,
              }))}
              onRouteHover={setHovered}
            />
          ) : (
            <div className="grid-backdrop h-full w-full animate-pulse" />
          )}
          {sorted.length > 0 && (
            <div className="absolute left-3 top-3 z-[1000] space-y-1.5 rounded-lg border border-border bg-panel/95 p-3 text-xs">
              <p className="eyebrow mb-1">Routes</p>
              {sorted.map((r) => (
                <div key={r.id} className="flex items-center gap-2">
                  <RouteSwatch route={r} className="size-4 text-[9px]" />
                  {ROUTE_TYPE_LABEL[r.routeType]}
                  {!r.feasible && (
                    <span className="text-muted-foreground">(not feasible, dashed)</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {computing && (
            <div className="absolute inset-0 z-[1100] flex items-center justify-center bg-background/50">
              <div className="flex items-center gap-2 rounded-full border border-border bg-panel px-4 py-2 text-sm">
                <Loader2 className="size-4 animate-spin text-sand" /> Computing routes…
              </div>
            </div>
          )}
        </div>

        <aside
          className="flex w-[460px] shrink-0 flex-col border-l border-border bg-panel/40"
          aria-label="Route alternatives"
        >
          <div className="flex items-center gap-2 border-b border-border px-5 py-3">
            <GitCompareArrows className="size-4 text-sand" />
            <h2 className="flex-1 text-sm font-semibold">Route alternatives</h2>
            {sorted.length > 0 && (
              <span className="text-xs text-muted-foreground">
                Hover a card to highlight its line
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {routes.isLoading || computing ? (
              Array.from({ length: 4 }, (_, i) => <PanelSkeleton key={i} rows={5} />)
            ) : routes.error ? (
              <ErrorState error={routes.error} onRetry={() => routes.refetch()} />
            ) : sorted.length === 0 ? (
              <EmptyState
                icon={<RouteIcon className="size-5" />}
                title="No routes yet"
                description={
                  finalized
                    ? "This mission is finalized without routes."
                    : "Calculate four route alternatives for this mission."
                }
              >
                {!finalized && (
                  <Button onClick={() => calculate.mutate()} disabled={busy || !m}>
                    Calculate routes
                  </Button>
                )}
              </EmptyState>
            ) : (
              sorted.map((r) => (
                <RouteCard
                  key={r.id}
                  route={r}
                  selected={r.id === m?.selectedRouteId}
                  highlighted={hovered === r.id}
                  onHover={setHovered}
                  onSelect={() => select.mutate(r.id)}
                  selecting={select.isPending && select.variables === r.id}
                  selectDisabled={busy || finalized || !r.feasible}
                  disabledReason={
                    finalized
                      ? "Mission is finalized."
                      : !r.feasible
                        ? "Not feasible routes cannot be selected."
                        : undefined
                  }
                />
              ))
            )}
            {!routes.isLoading && !computing && !routes.error && sorted.length > 0 && (
              <RouteRadar key={id} routes={sorted} hovered={hovered} onHover={setHovered} />
            )}
          </div>
          {sorted.length > 0 && (
            <div className="flex gap-2 border-t border-border p-4">
              <Button variant="outline" className="flex-1" asChild>
                <Link to="/missions/$id/edit" params={{ id: String(id) }}>
                  Add stops or warnings
                </Link>
              </Button>
              <Button className="flex-1" asChild>
                <Link to="/missions/$id/report" params={{ id: String(id) }}>
                  Open report
                </Link>
              </Button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
