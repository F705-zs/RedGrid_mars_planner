import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AlertCircle, ChevronDown, Loader2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { ApiError, buildCreateMissionBody } from "@/api/client";
import {
  useCreateMissionWithRoutes,
  usePlanningConstants,
  usePriorityPresets,
} from "@/api/queries";
import { ErrorState } from "@/components/common/states";
import { LazyMarsMap } from "@/components/map/LazyMarsMap";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { pointInRing, round6 } from "@/lib/geo";
import { PRIORITY_LABEL } from "@/lib/labels";
import {
  allPrioritiesZero,
  DEFAULT_CUSTOM_PRIORITIES,
  mixEntries,
  mixTotal,
  mixWeights,
  shareOf,
} from "@/lib/priorities";
import { useRegionContext } from "@/lib/region-context";
import { cn } from "@/lib/utils";
import type {
  MixPreset,
  Position,
  Priorities,
  PriorityPreset,
  Region,
  ResourcesInput,
} from "@/types";
import { PRIORITY_KEYS } from "@/types";

export const Route = createFileRoute("/missions/new")({
  head: () => ({
    meta: [
      { title: "New Mission — RedGrid" },
      {
        name: "description",
        content:
          "Set up a Mars walk: pick start and destination on the map, choose route priorities and generate four routes.",
      },
      { property: "og:title", content: "New Mission — RedGrid" },
      {
        property: "og:description",
        content: "Pick start and destination in Jezero Crater and generate route alternatives.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: MissionSetup,
});

type Which = "start" | "destination";

/** Inside the backend's routable area (null when the area is not provided: the backend decides). */
function routable(region: Region | undefined, p: Position | null): boolean | null {
  const a = region?.routableArea;
  if (!a || !p) return null;
  const polys = a.type === "Polygon" ? [a.coordinates] : a.coordinates;
  return polys.some(
    (rings) => pointInRing(p, rings[0]!) && !rings.slice(1).some((h) => pointInRing(p, h)),
  );
}

function CoordFields({
  which,
  value,
  onChange,
  active,
  onActivate,
  invalid,
  note,
}: {
  which: Which;
  value: { lon: string; lat: string };
  onChange: (v: { lon: string; lat: string }) => void;
  active: boolean;
  onActivate: () => void;
  invalid: boolean;
  note?: string | undefined;
}) {
  const label = which === "start" ? "Start" : "Destination";
  return (
    <div
      className={cn(
        "rounded-md border px-2.5 py-2",
        active ? "border-sand/70" : "border-border",
        invalid && "border-destructive",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <Button
          type="button"
          size="sm"
          variant={active ? "secondary" : "ghost"}
          onClick={onActivate}
          className="h-6 px-2 text-xs"
          aria-pressed={active}
        >
          {active ? "Placing on map" : "Place on map"}
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {(["lon", "lat"] as const).map((k) => (
          <div key={k}>
            <Label htmlFor={`${which}-${k}`} className="text-xs text-muted-foreground">
              {label} {k === "lon" ? "longitude (°E)" : "latitude (°N)"}
            </Label>
            <Input
              id={`${which}-${k}`}
              inputMode="decimal"
              className="data-value mt-0.5 h-8"
              value={value[k]}
              aria-invalid={invalid}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
              placeholder="—"
            />
          </div>
        ))}
      </div>
      {note && <p className="mt-1 text-xs text-warning">{note}</p>}
    </div>
  );
}

const toFields = (p: Position | null) => ({
  lon: p ? String(p[0]) : "",
  lat: p ? String(p[1]) : "",
});
const parse = (f: { lon: string; lat: string }): Position | null => {
  const lon = Number(f.lon);
  const lat = Number(f.lat);
  return f.lon.trim() && f.lat.trim() && Number.isFinite(lon) && Number.isFinite(lat)
    ? [lon, lat]
    : null;
};
const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

const RESOURCE_FIELDS = [
  { key: "oxygenKg", label: "Oxygen", unit: "kg", constant: "default_oxygen_kg", advanced: false },
  {
    key: "batteryWh",
    label: "Battery",
    unit: "Wh",
    constant: "default_battery_wh",
    advanced: false,
  },
  {
    key: "metabolicRateW",
    label: "Work rate",
    unit: "W",
    constant: "metabolic_rate_w",
    advanced: true,
  },
  {
    key: "suitPowerW",
    label: "Suit power",
    unit: "W",
    constant: "default_suit_power_w",
    advanced: true,
  },
] as const;

function MissionSetup() {
  const { region, error: regionError, refetch } = useRegionContext();
  const presets = usePriorityPresets();
  const constants = usePlanningConstants();
  const navigate = useNavigate();
  const create = useCreateMissionWithRoutes();

  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [start, setStart] = useState({ lon: "", lat: "" });
  const [dest, setDest] = useState({ lon: "", lat: "" });
  const [placing, setPlacing] = useState<Which>("start");
  const [profile, setProfile] = useState<PriorityPreset>("BALANCED");
  const [priorities, setPriorities] = useState<Priorities>(DEFAULT_CUSTOM_PRIORITIES);
  const [mix, setMix] = useState<Partial<Record<MixPreset, number>>>({});
  const [resources, setResources] = useState<Record<string, string>>({});
  const [reservePct, setReservePct] = useState("");
  const [startIsBase, setStartIsBase] = useState(true);
  const [advanced, setAdvanced] = useState(false);
  const [stage, setStage] = useState<"creating" | "routing" | null>(null);
  const [error, setError] = useState<{ error: ApiError | Error; missionId?: number } | null>(null);

  const startPos = parse(start);
  const destPos = parse(dest);
  const total = mixTotal(mix);
  const mixActive = profile === "CUSTOM" && total > 0;
  const mixInvalid = mixActive && Math.abs(total - 100) > 0.01;
  const customBlocked = profile === "CUSTOM" && (allPrioritiesZero(priorities) || mixInvalid);
  const selectedPreset = presets.data?.find((p) => p.key === profile);
  const errorField =
    error?.error instanceof ApiError ? String(error.error.details["field"] ?? "") : "";
  const constant = (k: string) => constants.data?.find((c) => c.key === k);
  const reserve = num(reservePct);
  const resourcesInvalid =
    Object.values(resources).some((v) => v.trim() !== "" && !(Number(v) >= 0)) ||
    (reserve !== undefined && !(reserve >= 0 && reserve < 100));

  const startRoutable = routable(region, startPos);
  const destRoutable = routable(region, destPos);

  const endpoints = useMemo(() => {
    const list = [];
    if (startPos)
      list.push({
        kind: "start" as const,
        position: startPos,
        draggable: true,
        onMove: (p: Position) => setStart(toFields(p)),
      });
    if (destPos)
      list.push({
        kind: "destination" as const,
        position: destPos,
        draggable: true,
        onMove: (p: Position) => setDest(toFields(p)),
      });
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, dest]);

  const onMapClick = (p: Position) => {
    const rounded: Position = [round6(p[0]), round6(p[1])];
    if (placing === "start") {
      setStart(toFields(rounded));
      if (!destPos) setPlacing("destination");
    } else setDest(toFields(rounded));
  };

  const setMixValue = (key: MixPreset, v: string) => {
    const next = { ...mix, [key]: Math.max(0, Math.min(100, Number(v) || 0)) };
    setMix(next);
    const w = presets.data ? mixWeights(next, presets.data) : null;
    if (w && Math.abs(mixTotal(next) - 100) <= 0.01) setPriorities(w); // fills the sliders; the user can fine-tune after
  };

  const missing = !name.trim()
    ? "Enter a mission name."
    : !startPos
      ? "Set a start point."
      : !destPos
        ? "Set a destination."
        : null;
  const pending = create.isPending;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!region || missing || customBlocked || resourcesInvalid || pending || !startPos || !destPos)
      return;
    setError(null);
    const res: ResourcesInput = {};
    for (const f of RESOURCE_FIELDS) {
      const v = num(resources[f.key] ?? "");
      if (v !== undefined) res[f.key] = v;
    }
    create.mutate(
      {
        body: buildCreateMissionBody({
          regionId: region.id,
          name: name.trim(),
          objective: objective.trim() || null,
          startLon: startPos[0],
          startLat: startPos[1],
          destLon: destPos[0],
          destLat: destPos[1],
          profile,
          priorities,
          priorityMix: mixActive ? mixEntries(mix) : [],
          ...(reserve !== undefined ? { reserveFraction: reserve / 100 } : {}),
          startIsBase,
          resources: res,
        }),
        onStage: setStage,
      },
      {
        onSuccess: ({ mission, routesError }) => {
          setStage(null);
          if (routesError) {
            setError({ error: routesError as Error, missionId: mission.id });
            return;
          }
          navigate({ to: "/missions/$id/routes", params: { id: String(mission.id) } });
        },
        onError: (err) => {
          setStage(null);
          setError({ error: err });
        },
      },
    );
  };

  if (regionError)
    return <ErrorState error={regionError} onRetry={() => void refetch()} className="m-6" />;

  const choices: { key: PriorityPreset; label: string }[] = [
    ...(presets.data ?? []).map((p) => ({ key: p.key as PriorityPreset, label: p.displayName })),
    { key: "CUSTOM", label: "Custom priorities" },
  ];

  return (
    <div className="flex min-h-0 flex-1">
      <form
        onSubmit={submit}
        className="flex w-[420px] shrink-0 flex-col border-r border-border bg-panel"
        noValidate
      >
        <div className="border-b border-border px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">New mission</h1>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <div className="space-y-2">
            <div>
              <Label htmlFor="mission-name">Mission name</Label>
              <Input
                id="mission-name"
                className="mt-1"
                value={name}
                maxLength={80}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Delta front traverse"
                aria-invalid={errorField === "name"}
              />
            </div>
            <div>
              <Label htmlFor="mission-objective">
                Objective <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="mission-objective"
                className="mt-1 min-h-0"
                rows={2}
                maxLength={500}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="e.g. Core the layered rock at the delta front"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Locations</Label>
            <CoordFields
              which="start"
              value={start}
              onChange={setStart}
              active={placing === "start"}
              onActivate={() => setPlacing("start")}
              invalid={errorField === "start" || errorField === "startLon"}
              note={
                startRoutable === false
                  ? "Outside the routable area: routes cannot start here."
                  : undefined
              }
            />
            <CoordFields
              which="destination"
              value={dest}
              onChange={setDest}
              active={placing === "destination"}
              onActivate={() => setPlacing("destination")}
              invalid={
                errorField === "dest" || errorField === "destination" || errorField === "destLon"
              }
              note={
                destRoutable === false
                  ? "Outside the routable area: routes cannot end here."
                  : undefined
              }
            />
            <p className="text-xs text-muted-foreground">
              Click the map or type coordinates; drag the markers to adjust.
            </p>
          </div>

          <div>
            <Label>Route priorities</Label>
            {presets.isLoading ? (
              <Skeleton className="mt-1 h-16 w-full" />
            ) : presets.error ? (
              <ErrorState
                error={presets.error}
                onRetry={() => presets.refetch()}
                className="mt-1 py-6"
              />
            ) : (
              <div
                className="mt-1 grid grid-cols-2 gap-1.5"
                role="radiogroup"
                aria-label="Route priorities"
              >
                {choices.map((c) => (
                  <button
                    key={c.key}
                    type="button"
                    role="radio"
                    aria-checked={profile === c.key}
                    onClick={() => setProfile(c.key)}
                    className={cn(
                      "rounded-md border px-2.5 py-1.5 text-left text-sm",
                      profile === c.key
                        ? "border-sand bg-sand/15"
                        : "border-border hover:bg-surface",
                    )}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            )}
            {selectedPreset && profile !== "CUSTOM" && (
              <p className="mt-1.5 text-xs text-muted-foreground">{selectedPreset.description}</p>
            )}
          </div>

          {profile === "CUSTOM" && (
            <section
              className="space-y-3 rounded-md border border-border p-3"
              aria-labelledby="custom-title"
            >
              <h2 id="custom-title" className="text-sm font-semibold">
                Custom priorities
              </h2>
              <div>
                <p className="text-xs text-muted-foreground">
                  Mix presets (percent, total 100), then fine-tune below.
                </p>
                <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1.5">
                  {(presets.data ?? []).map((p) => (
                    <label key={p.key} className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate">{p.displayName}</span>
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        step={5}
                        className="data-value h-7 w-16 text-right"
                        value={mix[p.key] ?? ""}
                        placeholder="0"
                        onChange={(e) => setMixValue(p.key, e.target.value)}
                        aria-label={`${p.displayName} percent`}
                      />
                    </label>
                  ))}
                </div>
                {total > 0 && (
                  <p
                    className={cn(
                      "mt-1 text-xs",
                      mixInvalid ? "text-destructive" : "text-muted-foreground",
                    )}
                    role={mixInvalid ? "alert" : undefined}
                  >
                    Mix total {total}%{mixInvalid ? " — must be 100%" : ""}
                  </p>
                )}
              </div>
              <div className="space-y-2.5">
                {PRIORITY_KEYS.map((k) => {
                  const share = shareOf(priorities, k);
                  return (
                    <div key={k}>
                      <div className="flex items-center justify-between text-sm">
                        <Label htmlFor={`w-${k}`}>{PRIORITY_LABEL[k]}</Label>
                        <span
                          className="data-value text-xs text-muted-foreground"
                          title={`Weight ${priorities[k].toFixed(3)}`}
                        >
                          {share === null ? "—" : `${Math.round(share * 100)}%`}
                        </span>
                      </div>
                      <Slider
                        id={`w-${k}`}
                        className="mt-1.5"
                        min={0}
                        max={1}
                        step={0.05}
                        value={[priorities[k]]}
                        onValueChange={([v]) => setPriorities((p) => ({ ...p, [k]: v }))}
                        aria-label={`${PRIORITY_LABEL[k]} weight`}
                      />
                    </div>
                  );
                })}
              </div>
              {allPrioritiesZero(priorities) && (
                <p className="flex items-center gap-1.5 text-xs text-destructive" role="alert">
                  <AlertCircle className="size-3.5" /> Set at least one priority above zero.
                </p>
              )}
            </section>
          )}

          <section className="space-y-2" aria-labelledby="res-title">
            <h2 id="res-title" className="text-sm font-medium">
              Oxygen and battery
            </h2>
            <div className="grid grid-cols-3 gap-2">
              {RESOURCE_FIELDS.filter((f) => !f.advanced).map((f) => {
                const c = constant(f.constant);
                return (
                  <div key={f.key}>
                    <Label htmlFor={`res-${f.key}`} className="text-xs text-muted-foreground">
                      {f.label} ({f.unit})
                    </Label>
                    <Input
                      id={`res-${f.key}`}
                      type="number"
                      min={0}
                      step="any"
                      className="data-value mt-0.5 h-8"
                      value={resources[f.key] ?? ""}
                      placeholder={c ? String(c.value) : "—"}
                      title={c ? `Empty = default ${c.value} ${f.unit} (${c.source})` : undefined}
                      onChange={(e) => setResources((r) => ({ ...r, [f.key]: e.target.value }))}
                    />
                  </div>
                );
              })}
              <div>
                <Label htmlFor="res-reserve" className="text-xs text-muted-foreground">
                  Reserve (%)
                </Label>
                <Input
                  id="res-reserve"
                  type="number"
                  min={0}
                  max={99}
                  step={1}
                  className="data-value mt-0.5 h-8"
                  value={reservePct}
                  placeholder={
                    constant("default_reserve_fraction")
                      ? String(Math.round(constant("default_reserve_fraction")!.value * 100))
                      : "—"
                  }
                  onChange={(e) => setReservePct(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Empty fields use the backend default (an assumption, labelled as such on every route).
            </p>
            <label className="flex items-center justify-between gap-3 text-sm">
              Start is a base (refills oxygen and battery)
              <Switch checked={startIsBase} onCheckedChange={setStartIsBase} />
            </label>
            <button
              type="button"
              onClick={() => setAdvanced((a) => !a)}
              aria-expanded={advanced}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronDown
                className={cn("size-3.5 transition-transform", !advanced && "-rotate-90")}
              />{" "}
              Advanced settings
            </button>
            {advanced && (
              <div className="grid grid-cols-2 gap-2">
                {RESOURCE_FIELDS.filter((f) => f.advanced).map((f) => {
                  const c = constant(f.constant);
                  return (
                    <div key={f.key}>
                      <Label htmlFor={`res-${f.key}`} className="text-xs text-muted-foreground">
                        {f.label} ({f.unit})
                      </Label>
                      <Input
                        id={`res-${f.key}`}
                        type="number"
                        min={0}
                        step="any"
                        className="data-value mt-0.5 h-8"
                        value={resources[f.key] ?? ""}
                        placeholder={c ? String(c.value) : "—"}
                        title={c ? `Empty = default ${c.value} ${f.unit} (${c.source})` : undefined}
                        onChange={(e) => setResources((r) => ({ ...r, [f.key]: e.target.value }))}
                      />
                    </div>
                  );
                })}
              </div>
            )}
            {resourcesInvalid && (
              <p className="text-xs text-destructive" role="alert">
                Values must be zero or more, and the reserve below 100%.
              </p>
            )}
          </section>

          {error && (
            <Alert variant="destructive" role="alert">
              <AlertCircle className="size-4" />
              <AlertTitle>
                {error.missionId
                  ? "Mission saved, but routes could not be computed"
                  : "Could not create mission"}
              </AlertTitle>
              <AlertDescription>
                <p>{error.error.message}</p>
                {error.error instanceof ApiError && (
                  <p className="data-value mt-1 text-[11px] opacity-80">{error.error.code}</p>
                )}
                {error.missionId && (
                  <Link
                    to="/missions/$id/routes"
                    params={{ id: String(error.missionId) }}
                    className="mt-2 inline-block underline"
                  >
                    Open the mission to retry
                  </Link>
                )}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <div className="border-t border-border px-4 py-3">
          {missing && <p className="mb-2 text-xs text-muted-foreground">{missing}</p>}
          <Button
            type="submit"
            className="w-full"
            disabled={!!missing || customBlocked || resourcesInvalid || pending || !region}
          >
            {pending && <Loader2 className="animate-spin" />}
            {stage === "creating"
              ? "Creating mission…"
              : stage === "routing"
                ? "Calculating routes…"
                : "Generate routes"}
          </Button>
        </div>
      </form>

      <div className="relative min-w-0 flex-1">
        {region ? (
          <LazyMarsMap
            key={region.id}
            region={region}
            endpoints={endpoints}
            onMapClick={onMapClick}
          />
        ) : (
          <div className="grid-backdrop h-full w-full animate-pulse" />
        )}
        <div className="pointer-events-none absolute left-1/2 top-3 z-[1000] -translate-x-1/2 rounded-full border border-border bg-panel/95 px-3 py-1 text-xs text-muted-foreground">
          Placing the{" "}
          <span className="font-medium text-foreground">
            {placing === "start" ? "start" : "destination"}
          </span>
          {region?.routableArea ? " · dashed outline = routable area" : ""}
        </div>
      </div>
    </div>
  );
}
