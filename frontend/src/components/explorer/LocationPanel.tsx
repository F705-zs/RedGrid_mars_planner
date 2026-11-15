import { ChevronDown, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { isApiError } from "@/api/client";
import { DataStateBadge } from "@/components/common/badges";
import { Value } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtDistance, fmtNumber, fmtSlope, fmtText, UNAVAILABLE } from "@/lib/format";
import { formatLonLat } from "@/lib/geo";
import { TERRAIN_CLASS_LABEL } from "@/lib/labels";
import type { LocationInfo, NearFeature, Position } from "@/types";

import { FeatureSwatch } from "./FeatureSwatch";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}

function Nearest({
  label,
  feature,
  distance,
  tag,
}: {
  label: string;
  feature: NearFeature | null;
  distance: number | null;
  tag?: string | undefined;
}) {
  return (
    <div className="flex items-center gap-2 py-1 text-sm">
      <span className="w-24 shrink-0 text-muted-foreground">{label}</span>
      {feature ? (
        <>
          <FeatureSwatch type={feature.featureType} />
          <span
            className="min-w-0 flex-1 truncate"
            title={feature.name ?? feature.code ?? undefined}
          >
            {feature.name ?? feature.code ?? UNAVAILABLE}
            {tag && <span className="ml-1 text-xs text-muted-foreground">({tag})</span>}
          </span>
          <Value className="text-xs">{fmtDistance(distance)}</Value>
        </>
      ) : (
        <Value className="text-xs">{UNAVAILABLE}</Value>
      )}
    </div>
  );
}

function Section({
  title,
  children,
  aside,
}: {
  title: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="border-b border-border px-4 py-3 last:border-b-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="eyebrow">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function More({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronDown className={`size-3.5 transition-transform ${open ? "" : "-rotate-90"}`} />{" "}
        {label}
      </button>
      {open && <div className="mt-1">{children}</div>}
    </div>
  );
}

function weatherLabel(info: LocationInfo): string {
  const e = info.environment;
  if (e.dataState === "DATA_UNAVAILABLE" || !e.window) return "No weather data for the demo window";
  return `Average over sols ${e.window.startSol}–${e.window.endSol} (historical, not live)`;
}

export function LocationPanel({
  point,
  info,
  isLoading,
  error,
  onClose,
}: {
  point: Position;
  info: LocationInfo | undefined;
  isLoading: boolean;
  error: unknown;
  onClose: () => void;
}) {
  const safe = info?.nearestSafePoint;
  return (
    <aside
      className="flex w-80 shrink-0 flex-col border-l border-border bg-panel"
      aria-label="Location details"
    >
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold">Location</h2>
          <p className="data-value text-xs text-muted-foreground">
            {formatLonLat(point[0], point[1], 4)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={onClose}
          aria-label="Close location panel"
        >
          <X />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-4 p-4" aria-busy="true">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-4 w-full" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-4 text-sm">
            <p className="font-medium text-destructive">
              {isApiError(error, "OUT_OF_REGION")
                ? "Outside the mapped region"
                : "Location data could not be loaded"}
            </p>
            <p className="mt-1 text-muted-foreground">
              {error instanceof Error ? error.message : String(error)}
            </p>
          </div>
        ) : info ? (
          <>
            <Section
              title="Terrain"
              aside={
                <span
                  className="flex items-center gap-1.5"
                  title={`Data quality: ${fmtText(info.dataQuality)}`}
                >
                  <DataStateBadge state={info.dataState} />
                </span>
              }
            >
              <dl>
                <Row label="Elevation">
                  <Value>{fmtNumber(info.elevationM, 0, "m")}</Value>
                </Row>
                <Row label="Slope">
                  <Value>{fmtSlope(info.slopeDeg)}</Value>
                </Row>
                <Row label="Roughness">
                  <Value>{fmtNumber(info.roughnessM, 2, "m")}</Value>
                </Row>
                <Row label="Terrain class">
                  <span className="inline-flex items-center gap-1.5">
                    <Value>
                      {info.terrainClass ? TERRAIN_CLASS_LABEL[info.terrainClass] : UNAVAILABLE}
                    </Value>
                    {info.terrainClass && <DataStateBadge state={info.terrainClassDataState} />}
                  </span>
                </Row>
                <Row label="Routes can go here">
                  {info.routable ? (
                    <span>Yes</span>
                  ) : (
                    <span
                      className="text-muted-foreground"
                      title="Outside the area with full terrain data: data unavailable for routing"
                    >
                      No (no full terrain data)
                    </span>
                  )}
                </Row>
                <Row label="Data quality">
                  <Value>{fmtText(info.dataQuality)}</Value>
                </Row>
              </dl>
              <More label="Geology and categories">
                <dl>
                  <Row label="Geology unit">
                    <Value>{fmtText(info.terrainUnit)}</Value>
                  </Row>
                </dl>
                {info.categories.length > 0 ? (
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {info.categories.map((c) => (
                      <li
                        key={c.key}
                        className="rounded border border-border px-1.5 py-0.5 text-[11px]"
                        title={c.group}
                      >
                        {c.displayName}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No routing categories at this point.
                  </p>
                )}
              </More>
            </Section>

            <Section title="Nearest">
              <Nearest
                label="Hazard"
                feature={info.nearestHazard}
                distance={info.distanceToNearestHazardM}
              />
              <Nearest
                label="Science target"
                feature={info.nearestScienceTarget}
                distance={info.distanceToNearestScienceTargetM}
              />
              <Nearest
                label="Safe point"
                feature={info.nearestSafePoint}
                distance={info.distanceToNearestSafePointM}
                tag={safe ? (safe.providesRefill ? "refill" : "shelter only") : undefined}
              />
              <Nearest
                label="Refill point"
                feature={info.nearestRefillPoint}
                distance={info.distanceToNearestRefillPointM}
              />
            </Section>

            <Section
              title="Environment"
              aside={<DataStateBadge state={info.environment.dataState} />}
            >
              <p className="mb-1 text-xs text-muted-foreground">{weatherLabel(info)}</p>
              <dl>
                <Row label="Temperature">
                  <Value>{fmtNumber(info.environment.temperature, 1, "°C")}</Value>
                </Row>
                <Row label="Wind">
                  <Value>{fmtNumber(info.environment.windSpeed, 1, "m/s")}</Value>
                </Row>
                <Row label="Dust">
                  <Value>{fmtText(info.environment.dustStatus)}</Value>
                </Row>
              </dl>
              <More label="More environment data">
                <dl>
                  <Row label="Pressure">
                    <Value>{fmtNumber(info.environment.pressure, 0, "Pa")}</Value>
                  </Row>
                  <Row label="Sols with data">
                    <Value>{fmtNumber(info.environment.solsWithData)}</Value>
                  </Row>
                  <Row label="Latest reading">
                    <Value>{fmtDate(info.environment.observedAt)}</Value>
                  </Row>
                  <Row label="Source">
                    <Value>{fmtText(info.environment.source)}</Value>
                  </Row>
                </dl>
                <p className="mt-1 text-xs text-muted-foreground">
                  Regional values, not a measurement at this exact point.
                </p>
              </More>
            </Section>
          </>
        ) : null}
      </div>
    </aside>
  );
}
