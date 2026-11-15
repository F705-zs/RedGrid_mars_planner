import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Info, Printer } from "lucide-react";
import type { ReactNode } from "react";

import { isApiError } from "@/api/client";
import { useReport } from "@/api/queries";
import { FeasibleBadge, RiskBadge, StatusBadge } from "@/components/common/badges";
import { EmptyState, ErrorState, PanelSkeleton, Value } from "@/components/common/states";
import { MissionHeader } from "@/components/mission/MissionHeader";
import { RouteSwatch } from "@/components/mission/RouteCard";
import { useMissionPage } from "@/components/mission/use-mission-page";
import { Button } from "@/components/ui/button";
import {
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtKg,
  fmtKm,
  fmtMultiplier,
  fmtNumber,
  fmtShare,
  fmtSlope,
  fmtText,
  fmtWh,
  NOT_CHECKED,
  titleCase,
} from "@/lib/format";
import { formatLonLat } from "@/lib/geo";
import {
  ANNOTATION_LABEL,
  INPUT_SOURCE_LABEL,
  LIMITING_RESOURCE_LABEL,
  PRESET_LABEL,
  PRIORITY_LABEL,
  ROUTE_TYPE_LABEL,
  SEVERITY_LABEL,
} from "@/lib/labels";
import { useRegionById } from "@/lib/region-context";
import { cn } from "@/lib/utils";
import type { Report, Route as RouteT } from "@/types";
import { PRIORITY_KEYS, ROUTE_TYPES } from "@/types";

export const Route = createFileRoute("/missions/$id/report")({
  head: () => ({
    meta: [
      { title: "Mission Report — RedGrid" },
      {
        name: "description",
        content:
          "Printable one-page Mars mission report: summary, recommended route, route comparison, annotations and sources.",
      },
      { property: "og:title", content: "Mission Report — RedGrid" },
      { property: "og:description", content: "One-page printable report for a planned Mars walk." },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ReportPage,
});

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("print-avoid-break", className)}>
      <h2 className="mb-2 border-b border-border pb-1 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const th = "px-2 py-1.5 text-left font-medium text-muted-foreground";
const td = "px-2 py-1.5 align-top";
const tableText = "w-full text-[13.5px]";
const meta = "text-[12.5px] text-muted-foreground";

function ReportDoc({ report }: { report: Report }) {
  const { mission: m, recommendedRoute: rec, resources: res } = report;
  const region = useRegionById(m.regionId);
  const routes = [...report.routes].sort(
    (a, b) => ROUTE_TYPES.indexOf(a.routeType) - ROUTE_TYPES.indexOf(b.routeType),
  );
  const isSelected = !!rec && rec.id === m.selectedRouteId;

  const metrics: [string, string][] = rec
    ? [
        ["Distance", fmtKm(rec.distanceM)],
        ["Duration", fmtDuration(rec.durationMin)],
        ["Avg / max slope", `${fmtSlope(rec.averageSlopeDeg)} / ${fmtSlope(rec.maxSlopeDeg)}`],
        [
          "Elevation gain / loss",
          `${fmtNumber(rec.elevationGainM, 0, "m")} / ${fmtNumber(rec.elevationLossM, 0, "m")}`,
        ],
        ["Hazards", fmtNumber(rec.hazardCount)],
        ["Science score", fmtShare(rec.scienceScore)],
        ["Mission match", `${rec.missionMatch}%`],
        ["Terrain difficulty", fmtMultiplier(rec.terrainDifficulty)],
        ["Oxygen used / left", `${fmtKg(rec.oxygenUsedKg)} / ${fmtKg(rec.oxygenLeftKg)}`],
        ["Battery used / left", `${fmtWh(rec.batteryUsedWh)} / ${fmtWh(rec.batteryLeftWh)}`],
      ]
    : [];

  return (
    <article className="panel print-tight mx-auto max-w-[960px] space-y-6 p-8 print:border-0">
      <header className="flex items-start justify-between gap-6 border-b border-border pb-4">
        <div>
          <p className={meta}>RedGrid · Mission report</p>
          <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">{m.name}</h1>
          {m.objective && <p className="mt-1 text-[15px]">{m.objective}</p>}
          <p className={cn("mt-1", meta)}>
            Mission {m.id} · {region?.name ?? `Region ${m.regionId}`}
          </p>
        </div>
        <StatusBadge status={m.status} />
      </header>

      <Section title="Mission summary">
        <dl className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-[15px] md:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Start</dt>
            <dd className="data-value">{formatLonLat(m.startLon, m.startLat)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Destination</dt>
            <dd className="data-value">{formatLonLat(m.destLon, m.destLat)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Profile</dt>
            <dd>{PRESET_LABEL[m.profile]}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Coordinate system</dt>
            <dd className="text-xs">{region?.coordinateSystem ?? "—"}</dd>
          </div>
        </dl>
        <p className={cn("mt-2", meta)}>
          Priorities:{" "}
          {PRIORITY_KEYS.map((k) => `${PRIORITY_LABEL[k]} ${m.priorities[k]}`).join(" · ")}
          {m.priorityMix.length > 0 &&
            ` (mixed from ${m.priorityMix.map((e) => `${PRESET_LABEL[e.presetKey]} ${e.percent}%`).join(", ")})`}
        </p>
      </Section>

      {rec ? (
        <Section
          title={
            isSelected
              ? "Selected route"
              : "Recommended route (not selected: best feasible match shown)"
          }
        >
          <div className="flex flex-wrap items-center gap-2">
            <RouteSwatch route={rec} />
            <span className="text-[15px] font-semibold">{ROUTE_TYPE_LABEL[rec.routeType]}</span>
            <RiskBadge risk={rec.overallRisk} />
            <FeasibleBadge feasible={rec.feasible} />
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-[15px] md:grid-cols-4">
            {metrics.map(([k, v]) => (
              <div key={k}>
                <dt className={meta}>{k}</dt>
                <dd>
                  <Value>{v}</Value>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[15px]">{rec.recommendation}</p>
          <p className={cn("mt-1", meta)}>
            Return:{" "}
            {rec.returnFeasibility
              ? `${rec.returnFeasibility.feasible ? "feasible" : "not feasible"} — ${fmtDistance(rec.returnFeasibility.distanceToSafePointM)} to ${rec.returnFeasibility.refillPointName ?? rec.returnFeasibility.safePointName ?? "a refill point"}${rec.returnFeasibility.limitingResource !== "NONE" ? ` (limited by ${LIMITING_RESOURCE_LABEL[rec.returnFeasibility.limitingResource].toLowerCase()})` : ""}`
              : NOT_CHECKED}{" "}
            · Dust: {rec.assessment.dustStatus} · Comms: {rec.assessment.communicationStatus} · Data
            confidence: {fmtShare(rec.assessment.dataConfidence)} · Costs: {rec.costProvider.name}{" "}
            {rec.costProvider.version}
          </p>
          {rec.warnings.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[13.5px]">
              {rec.warnings.map((w, i) => (
                <li key={i} className="flex gap-1.5">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  {w}
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : (
        <Section title="Recommended route">
          <p className="flex items-center gap-2 text-[15px]">
            <AlertTriangle className="size-4 text-warning" /> No route is feasible with the current
            oxygen, battery and hazards. See the comparison below for the reasons.
          </p>
        </Section>
      )}

      <Section title="Route comparison">
        <table className={tableText}>
          <thead className="border-b border-border">
            <tr>
              <th className={th}>Route</th>
              <th className={th}>Feasible</th>
              <th className={th}>Risk</th>
              <th className={th}>Match</th>
              <th className={th}>Distance</th>
              <th className={th}>Duration</th>
              <th className={th}>Max slope</th>
              <th className={th}>Hazards</th>
              <th className={th}>Science</th>
              <th className={th}>Return</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {routes.map((r: RouteT) => (
              <tr key={r.id} className={cn(r.id === rec?.id && "bg-surface/60")}>
                <td className={td}>
                  <span className="flex items-center gap-1.5">
                    <RouteSwatch route={r} className="size-4 text-[9px]" />
                    {ROUTE_TYPE_LABEL[r.routeType]}
                  </span>
                </td>
                <td className={td}>{r.feasible ? "Yes" : "No"}</td>
                <td className={td}>{titleCase(r.overallRisk)}</td>
                <td className={cn(td, "data-value")}>{r.missionMatch}%</td>
                <td className={cn(td, "data-value")}>{fmtKm(r.distanceM)}</td>
                <td className={cn(td, "data-value")}>{fmtDuration(r.durationMin)}</td>
                <td className={cn(td, "data-value")}>{fmtSlope(r.maxSlopeDeg)}</td>
                <td className={cn(td, "data-value")}>{fmtNumber(r.hazardCount)}</td>
                <td className={cn(td, "data-value")}>{fmtShare(r.scienceScore)}</td>
                <td className={td}>
                  {r.returnFeasibility
                    ? r.returnFeasibility.feasible
                      ? "Feasible"
                      : "Not feasible"
                    : NOT_CHECKED}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Oxygen and battery">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[15px] md:grid-cols-4">
          {(
            [
              ["Oxygen", fmtKg(res.oxygenKg.value), res.oxygenKg.source],
              ["Battery", fmtWh(res.batteryWh.value), res.batteryWh.source],
              ["Work rate", fmtNumber(res.metabolicRateW.value, 0, "W"), res.metabolicRateW.source],
              ["Suit power", fmtNumber(res.suitPowerW.value, 0, "W"), res.suitPowerW.source],
            ] as const
          ).map(([k, v, src]) => (
            <div key={k}>
              <dt className={meta}>{k}</dt>
              <dd>
                <Value>{v}</Value> <span className={meta}>({INPUT_SOURCE_LABEL[src]})</span>
              </dd>
            </div>
          ))}
        </dl>
        <p className={cn("mt-1", meta)}>
          Reserve {fmtShare(res.reserveFraction)} · usable {fmtKg(res.usableOxygenKg)} oxygen and{" "}
          {fmtWh(res.usableBatteryWh)} battery ·{" "}
          {res.startIsBase ? "start is a base (refill)" : "start is not a base"}
        </p>
      </Section>

      <div className="grid gap-6 md:grid-cols-2 print:grid-cols-2">
        <Section title="Annotations">
          {report.annotations.length === 0 ? (
            <p className={meta}>No science stops or hazard warnings.</p>
          ) : (
            <table className={tableText}>
              <tbody className="divide-y divide-border/60">
                {report.annotations.map((a) => (
                  <tr key={a.id}>
                    <td className={td}>{ANNOTATION_LABEL[a.kind]}</td>
                    <td className={td}>{a.note || "No note"}</td>
                    <td className={cn(td, "data-value whitespace-nowrap")}>
                      {a.kind === "SCIENCE_STOP"
                        ? fmtDuration(a.durationMin)
                        : `${a.severity ? SEVERITY_LABEL[a.severity] : "Unknown"} · ${fmtDistance(a.radiusM)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
        <Section title="Data sources">
          <table className={tableText}>
            <tbody className="divide-y divide-border/60">
              {report.sources.map((d) => (
                <tr key={d.id}>
                  <td className={td}>
                    {d.name}
                    <div className={meta}>
                      {d.provider} · {fmtText(d.licence)}
                    </div>
                  </td>
                  <td className={cn(td, "whitespace-nowrap")}>
                    {fmtText(d.format)} · {fmtDistance(d.resolutionM)}
                  </td>
                  <td className={cn(td, "data-value")}>{d.doi ?? "No DOI"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      <div className="grid gap-6 md:grid-cols-2 print:grid-cols-2">
        <Section title="Method and providers">
          <dl className="grid grid-cols-[9rem_1fr] gap-y-1 text-[13.5px]">
            <dt className="text-muted-foreground">Weight model</dt>
            <dd>
              Version {report.costModel.version} · {titleCase(report.costModel.method)} ·{" "}
              {titleCase(report.costModel.status)}
            </dd>
            <dt className="text-muted-foreground">Training sources</dt>
            <dd>
              {report.trainingSources.length
                ? report.trainingSources.map((d) => d.name).join("; ")
                : "None (hand-set version)"}
            </dd>
            <dt className="text-muted-foreground">Providers used</dt>
            <dd>
              {report.providersUsed
                .map(
                  (p) =>
                    `${p.name} ${p.version} (${titleCase(p.kind)}, ${p.transport.toLowerCase()})`,
                )
                .join("; ")}
            </dd>
            <dt className="text-muted-foreground">Weather window</dt>
            <dd>
              {report.demoWindow
                ? `Sols ${report.demoWindow.startSol}–${report.demoWindow.endSol} (${fmtDate(report.demoWindow.startUtc)} to ${fmtDate(report.demoWindow.endUtc)}), ${report.demoWindow.source}`
                : "Not available"}
            </dd>
          </dl>
        </Section>
        <Section title="Terrain classes">
          <table className={tableText}>
            <tbody className="divide-y divide-border/60">
              {report.terrainClassMapping.map((t) => (
                <tr key={t.unitSymbol}>
                  <td className={cn(td, "data-value")}>{t.unitSymbol}</td>
                  <td className={td}>{t.unitName}</td>
                  <td className={td}>{titleCase(t.terrainClass)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      <Section title="Planning constants">
        <table className={tableText}>
          <thead className="border-b border-border">
            <tr>
              <th className={th}>Constant</th>
              <th className={th}>Value</th>
              <th className={th}>Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {report.constants.map((c) => (
              <tr key={c.key}>
                <td className={td}>
                  <span className="data-value">{c.key}</span>
                  <div className={meta}>{c.description}</div>
                </td>
                <td className={cn(td, "data-value whitespace-nowrap")}>
                  {c.value} {c.unit}
                </td>
                <td className={cn(td, meta)}>{c.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {report.caveats.length > 0 && (
        <Section title="Caveats">
          <ul className="list-disc space-y-1 pl-5 text-[14px]">
            {report.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </Section>
      )}

      <footer className="print-avoid-break flex gap-2 rounded-lg border border-sand/40 bg-sand/10 p-3 text-[13px]">
        <Info className="mt-0.5 size-4 shrink-0 text-sand" />
        <p>{report.notice}</p>
      </footer>
    </article>
  );
}

function ReportPage() {
  const { id: idParam } = Route.useParams();
  const { id, mission } = useMissionPage(idParam);
  const report = useReport(id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MissionHeader
        id={id}
        mission={mission.data}
        actions={
          report.data && (
            <Button onClick={() => window.print()}>
              <Printer /> Print
            </Button>
          )
        }
      />
      <div className="flex-1 p-6 print:p-0">
        {report.isLoading ? (
          <div className="mx-auto max-w-[960px] space-y-4">
            <PanelSkeleton rows={3} />
            <PanelSkeleton rows={6} />
            <PanelSkeleton rows={5} />
          </div>
        ) : isApiError(report.error, "ROUTES_NOT_CALCULATED") ? (
          <EmptyState
            title="No routes calculated yet"
            description="The report needs route alternatives. Calculate them first."
            className="mx-auto max-w-xl"
          >
            <Button asChild>
              <Link to="/missions/$id/routes" params={{ id: String(id) }}>
                Go to route comparison
              </Link>
            </Button>
          </EmptyState>
        ) : report.error ? (
          <ErrorState
            error={report.error}
            onRetry={() => report.refetch()}
            className="mx-auto max-w-xl"
          />
        ) : report.data ? (
          <ReportDoc report={report.data} />
        ) : null}
      </div>
    </div>
  );
}
