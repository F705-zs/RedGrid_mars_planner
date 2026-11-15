import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  AlertTriangle,
  FlaskConical,
  Loader2,
  MousePointerClick,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  useAnnotations,
  useCreateAnnotation,
  useDeleteAnnotation,
  useRecalculateRoutes,
  useRoutes,
} from "@/api/queries";
import { ErrorState, PanelSkeleton } from "@/components/common/states";
import { LazyMarsMap } from "@/components/map/LazyMarsMap";
import { FinalizedBanner } from "@/components/mission/FinalizedBanner";
import { MissionHeader } from "@/components/mission/MissionHeader";
import { useMissionMapLayers } from "@/components/mission/use-mission-map-layers";
import { useMissionPage } from "@/components/mission/use-mission-page";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { fmtDistance, fmtDuration } from "@/lib/format";
import { formatLonLat } from "@/lib/geo";
import { ANNOTATION_LABEL, SEVERITY_LABEL } from "@/lib/labels";
import type { AnnotationKind, CreateAnnotationBody, Position, Severity } from "@/types";

export const Route = createFileRoute("/missions/$id/edit")({
  head: () => ({
    meta: [
      { title: "Route Edit — RedGrid" },
      {
        name: "description",
        content:
          "Add science stops and hazard warnings to a Mars mission and recalculate its routes.",
      },
      { property: "og:title", content: "Route Edit — RedGrid" },
      {
        property: "og:description",
        content: "Annotate a Mars mission map with science stops and hazard warnings.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: RouteEdit,
});

interface Draft {
  position: Position;
  kind: AnnotationKind;
  note: string;
  durationMin: string;
  severity: Severity;
  radiusM: string;
}

function RouteEdit() {
  const { id: idParam } = Route.useParams();
  const navigate = useNavigate();
  const { id, mission, region, finalized } = useMissionPage(idParam);
  const annotations = useAnnotations(id);
  const routes = useRoutes(id);
  const create = useCreateAnnotation(id);
  const remove = useDeleteAnnotation(id);
  const recalc = useRecalculateRoutes(id);
  const contextLayers = useMissionMapLayers(region?.id);
  const [draft, setDraft] = useState<Draft | null>(null);

  const m = mission.data;
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
  const selected = routes.data?.find((r) => r.id === m?.selectedRouteId);
  const shownRoutes = (selected ? [selected] : (routes.data ?? [])).map((r) => ({
    route: r,
    dimmed: !selected,
  }));

  if (mission.error) return <ErrorState error={mission.error} className="m-6" />;

  const radius = Number(draft?.radiusM);
  const duration = Number(draft?.durationMin);
  const draftInvalid =
    !draft ||
    (draft.kind === "SCIENCE_STOP"
      ? !Number.isFinite(duration) || duration < 1 || duration > 600
      : !Number.isFinite(radius) || radius < 10 || radius > 5000);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!draft || draftInvalid || finalized) return;
    const body: CreateAnnotationBody =
      draft.kind === "SCIENCE_STOP"
        ? {
            kind: "SCIENCE_STOP",
            lon: draft.position[0],
            lat: draft.position[1],
            note: draft.note.trim(),
            durationMin: duration,
          }
        : {
            kind: "HAZARD_WARNING",
            lon: draft.position[0],
            lat: draft.position[1],
            note: draft.note.trim(),
            severity: draft.severity,
            radiusM: radius,
          };
    create.mutate(body, {
      onSuccess: () => {
        toast.success(`${ANNOTATION_LABEL[draft.kind]} added`);
        setDraft(null);
      },
    });
  };

  const doRecalc = () =>
    recalc.mutate(undefined, {
      onSuccess: () => {
        toast.success("Routes recalculated. Select a route again.");
        navigate({ to: "/missions/$id/routes", params: { id: String(id) } });
      },
    });

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
              routes={shownRoutes}
              annotations={annotations.data ?? []}
              endpoints={[
                { kind: "start", position: [m.startLon, m.startLat] },
                { kind: "destination", position: [m.destLon, m.destLat] },
              ]}
              draftAnnotation={
                draft
                  ? {
                      kind: draft.kind,
                      position: draft.position,
                      radiusM: Number(draft.radiusM) || null,
                    }
                  : null
              }
              onMapClick={
                finalized
                  ? undefined
                  : (p) =>
                      setDraft((d) => ({
                        ...(d ?? {
                          kind: "SCIENCE_STOP",
                          note: "",
                          durationMin: "30",
                          severity: "MEDIUM",
                          radiusM: "250",
                        }),
                        position: p,
                      }))
              }
              fitTo={fitTo}
            />
          ) : (
            <div className="grid-backdrop h-full w-full animate-pulse" />
          )}
          {!finalized && !draft && (
            <div className="pointer-events-none absolute left-1/2 top-3 z-[1000] flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-panel/95 px-3 py-1.5 text-xs text-muted-foreground">
              <MousePointerClick className="size-3.5 text-sand" /> Click the map to add a science
              stop or hazard warning
            </div>
          )}
        </div>

        <aside className="flex w-[420px] shrink-0 flex-col border-l border-border bg-panel/40">
          {draft && !finalized && (
            <form onSubmit={submit} className="space-y-4 border-b border-border bg-panel p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">New annotation</h2>
                <span className="data-value text-xs text-muted-foreground">
                  {formatLonLat(draft.position[0], draft.position[1], 4)}
                </span>
              </div>
              <ToggleGroup
                type="single"
                value={draft.kind}
                onValueChange={(v) => v && setDraft({ ...draft, kind: v as AnnotationKind })}
                className="grid grid-cols-2"
                variant="outline"
              >
                <ToggleGroupItem value="SCIENCE_STOP" className="gap-1.5">
                  <FlaskConical className="size-4 text-map-science" /> Science stop
                </ToggleGroupItem>
                <ToggleGroupItem value="HAZARD_WARNING" className="gap-1.5">
                  <AlertTriangle className="size-4 text-map-hazard" /> Hazard warning
                </ToggleGroupItem>
              </ToggleGroup>
              <div>
                <Label htmlFor="ann-note">Note</Label>
                <Textarea
                  id="ann-note"
                  className="mt-1.5"
                  rows={2}
                  maxLength={500}
                  value={draft.note}
                  onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                />
              </div>
              {draft.kind === "SCIENCE_STOP" ? (
                <div>
                  <Label htmlFor="ann-duration">Stop duration (minutes)</Label>
                  <Input
                    id="ann-duration"
                    type="number"
                    min={1}
                    max={600}
                    className="mt-1.5"
                    value={draft.durationMin}
                    onChange={(e) => setDraft({ ...draft, durationMin: e.target.value })}
                  />
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="ann-severity">Severity</Label>
                    <Select
                      value={draft.severity}
                      onValueChange={(v) => setDraft({ ...draft, severity: v as Severity })}
                    >
                      <SelectTrigger id="ann-severity" className="mt-1.5">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(["LOW", "MEDIUM", "HIGH"] as Severity[]).map((s) => (
                          <SelectItem key={s} value={s}>
                            {SEVERITY_LABEL[s]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="ann-radius">Radius (m)</Label>
                    <Input
                      id="ann-radius"
                      type="number"
                      min={10}
                      max={5000}
                      className="mt-1.5"
                      value={draft.radiusM}
                      onChange={(e) => setDraft({ ...draft, radiusM: e.target.value })}
                    />
                  </div>
                </div>
              )}
              {draftInvalid && (
                <p className="text-xs text-destructive">
                  {draft.kind === "SCIENCE_STOP"
                    ? "Duration must be 1–600 minutes."
                    : "Radius must be 10–5000 m."}
                </p>
              )}
              <div className="flex gap-2">
                <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="flex-1"
                  disabled={draftInvalid || create.isPending}
                >
                  {create.isPending && <Loader2 className="animate-spin" />} Add{" "}
                  {ANNOTATION_LABEL[draft.kind].toLowerCase()}
                </Button>
              </div>
            </form>
          )}

          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="text-sm font-semibold">Annotations</h2>
            <span className="data-value text-xs text-muted-foreground">
              {annotations.data?.length ?? 0}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {annotations.isLoading ? (
              <PanelSkeleton className="m-4" />
            ) : annotations.error ? (
              <ErrorState
                error={annotations.error}
                onRetry={() => annotations.refetch()}
                className="m-4"
              />
            ) : !annotations.data?.length ? (
              <p className="px-5 py-8 text-center text-sm text-muted-foreground">
                No science stops or hazard warnings yet.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {annotations.data.map((a) => (
                  <li key={a.id} className="flex items-start gap-3 px-5 py-3">
                    {a.kind === "SCIENCE_STOP" ? (
                      <FlaskConical
                        className="mt-0.5 size-4 shrink-0 text-map-science"
                        aria-hidden
                      />
                    ) : (
                      <AlertTriangle
                        className="mt-0.5 size-4 shrink-0 text-map-hazard"
                        aria-hidden
                      />
                    )}
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-medium">{ANNOTATION_LABEL[a.kind]}</p>
                      <p className="text-muted-foreground">{a.note || "No note"}</p>
                      <p className="data-value mt-1 text-xs text-muted-foreground">
                        {a.kind === "SCIENCE_STOP"
                          ? fmtDuration(a.durationMin)
                          : `${a.severity ? SEVERITY_LABEL[a.severity] : "Unknown"} severity · ${fmtDistance(a.radiusM)} radius`}{" "}
                        · {formatLonLat(a.lon, a.lat, 3)}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${ANNOTATION_LABEL[a.kind].toLowerCase()}`}
                      disabled={finalized || (remove.isPending && remove.variables === a.id)}
                      onClick={() =>
                        remove.mutate(a.id, {
                          onSuccess: () => toast.success("Annotation deleted"),
                        })
                      }
                    >
                      {remove.isPending && remove.variables === a.id ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Trash2 />
                      )}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-border p-4">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button className="w-full" disabled={finalized || recalc.isPending || !m}>
                  {recalc.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                  {recalc.isPending ? "Recalculating…" : "Recalculate routes"}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Recalculate routes?</AlertDialogTitle>
                  <AlertDialogDescription>
                    All four routes are replaced using the current annotations.
                    {m?.selectedRouteId
                      ? " Your selected route will be cleared and you'll need to select one again."
                      : " The selected route, if any, will be cleared."}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={doRecalc}>Recalculate</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <p className="mt-2 text-center text-xs text-muted-foreground">
              New annotations affect routes only after recalculating.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
