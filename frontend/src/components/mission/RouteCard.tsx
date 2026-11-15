import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { FeasibleBadge, RiskBadge } from "@/components/common/badges";
import { Value } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  fmtDistance,
  fmtDuration,
  fmtKg,
  fmtKm,
  fmtMultiplier,
  fmtNumber,
  fmtShare,
  fmtSlope,
  fmtWh,
  NOT_CHECKED,
} from "@/lib/format";
import { LIMITING_RESOURCE_LABEL } from "@/lib/labels";
import { ROUTE_TYPE_CODE, ROUTE_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Route } from "@/types";

export function RouteSwatch({
  route,
  className,
}: {
  route: Pick<Route, "routeType" | "feasible">;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex size-6 shrink-0 items-center justify-center rounded font-mono text-[11px] font-bold text-background",
        `rg-swatch--${route.routeType}`,
        !route.feasible && "border-2 border-dashed border-foreground bg-panel! text-foreground",
        className,
      )}
      aria-hidden
    >
      {ROUTE_TYPE_CODE[route.routeType]}
    </span>
  );
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow text-[9px]">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{children}</dd>
    </div>
  );
}

export function RouteCard({
  route,
  selected,
  highlighted,
  onHover,
  onSelect,
  selecting,
  selectDisabled,
  disabledReason,
}: {
  route: Route;
  selected: boolean;
  highlighted: boolean;
  onHover: (id: number | null) => void;
  onSelect: () => void;
  selecting: boolean;
  selectDisabled: boolean;
  disabledReason?: string | undefined;
}) {
  const rf = route.returnFeasibility;
  return (
    <article
      onMouseEnter={() => onHover(route.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(route.id)}
      onBlur={() => onHover(null)}
      className={cn(
        "panel overflow-hidden transition-colors",
        highlighted && "border-foreground/40",
        selected && "border-mars ring-1 ring-mars",
        !route.feasible && "border-dashed",
      )}
      aria-label={`${ROUTE_TYPE_LABEL[route.routeType]} route`}
    >
      <header className="flex items-center gap-3 border-b border-border px-4 py-3">
        <RouteSwatch route={route} />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">{ROUTE_TYPE_LABEL[route.routeType]}</h3>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <RiskBadge risk={route.overallRisk} />
            <FeasibleBadge feasible={route.feasible} />
          </div>
        </div>
        <div className="text-right">
          <p className="data-value text-2xl font-semibold leading-none">{route.missionMatch}%</p>
          <p className="eyebrow mt-1 text-[9px]">Mission match</p>
        </div>
      </header>

      <dl className="grid grid-cols-3 gap-x-3 gap-y-3 px-4 py-3">
        <Metric label="Distance">
          <Value>{fmtKm(route.distanceM)}</Value>
        </Metric>
        <Metric label="Duration">
          <Value>{fmtDuration(route.durationMin)}</Value>
        </Metric>
        <Metric label="Hazards">
          <Value>{fmtNumber(route.hazardCount)}</Value>
        </Metric>
        <Metric label="Avg slope">
          <Value>{fmtSlope(route.averageSlopeDeg)}</Value>
        </Metric>
        <Metric label="Max slope">
          <Value>{fmtSlope(route.maxSlopeDeg)}</Value>
        </Metric>
        <Metric label="Science">
          <Value>{fmtShare(route.scienceScore)}</Value>
        </Metric>
        <Metric label="Elev. gain">
          <Value>{fmtNumber(route.elevationGainM, 0, "m")}</Value>
        </Metric>
        <Metric label="Elev. loss">
          <Value>{fmtNumber(route.elevationLossM, 0, "m")}</Value>
        </Metric>
        <Metric label="Terrain">
          <Value>{fmtMultiplier(route.terrainDifficulty)}</Value>
        </Metric>
        <Metric label="O₂ left">
          <Value>{fmtKg(route.oxygenLeftKg)}</Value>
        </Metric>
        <Metric label="Battery left">
          <Value>{fmtWh(route.batteryLeftWh)}</Value>
        </Metric>
        <Metric label="O₂ used">
          <Value>{fmtKg(route.oxygenUsedKg)}</Value>
        </Metric>
      </dl>

      <div className="space-y-2 border-t border-border px-4 py-3 text-xs">
        <div className="grid grid-cols-[7.5rem_1fr] gap-y-1">
          <span className="text-muted-foreground">Dust</span>
          <span>{route.assessment.dustStatus}</span>
          <span className="text-muted-foreground">Communication</span>
          <span>{route.assessment.communicationStatus}</span>
          <span className="text-muted-foreground">Data confidence</span>
          <span>{fmtShare(route.assessment.dataConfidence)}</span>
          <span className="text-muted-foreground">Return</span>
          {rf ? (
            <span>
              {rf.feasible ? "Feasible" : "Not feasible"} · {fmtDistance(rf.distanceToSafePointM)}{" "}
              to {rf.refillPointName ?? rf.safePointName ?? "a refill point"} (
              {fmtDuration(rf.returnDurationMin)}, limit {fmtDistance(rf.maximumReturnDistanceM)})
              {rf.limitingResource !== "NONE" &&
                ` · limited by ${LIMITING_RESOURCE_LABEL[rf.limitingResource].toLowerCase()}`}
            </span>
          ) : (
            <span className="italic text-muted-foreground">{NOT_CHECKED}</span>
          )}
          <span className="text-muted-foreground">Costs</span>
          <span>
            {route.costProvider.name} {route.costProvider.version}
            {route.costProvider.kind === "MODEL" ? " (model)" : ""}
          </span>
        </div>
        {rf?.reason && <p className="text-muted-foreground">{rf.reason}</p>}
      </div>

      {route.warnings.length > 0 && (
        <ul className="space-y-1 border-t border-border bg-warning/5 px-4 py-3 text-xs">
          {route.warnings.map((w, i) => (
            <li key={i} className="flex gap-1.5">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}

      <footer className="flex items-center gap-3 border-t border-border px-4 py-3">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">{route.recommendation}</p>
        {selected ? (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-mars">
            <CheckCircle2 className="size-4" /> Selected
          </span>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={onSelect}
            disabled={selectDisabled}
            title={disabledReason}
          >
            {selecting && <Loader2 className="animate-spin" />}
            Select this route
          </Button>
        )}
      </footer>
      {disabledReason && !selected && (
        <p className="px-4 pb-3 text-right text-[11px] text-muted-foreground">{disabledReason}</p>
      )}
    </article>
  );
}
