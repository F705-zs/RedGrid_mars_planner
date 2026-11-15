import { Link } from "@tanstack/react-router";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/common/badges";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { formatLonLat } from "@/lib/geo";
import { PRESET_LABEL } from "@/lib/labels";
import type { Mission } from "@/types";

const TABS = [
  { to: "/missions/$id/routes", label: "Compare" },
  { to: "/missions/$id/edit", label: "Edit" },
  { to: "/missions/$id/report", label: "Report" },
] as const;

/** Mission details that are useful but repetitive on screen: kept one click away. */
function MissionDetails({ mission }: { mission: Mission }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs text-muted-foreground">
          <Info className="size-3.5" /> Details
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 text-xs">
        <dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1.5">
          <dt className="text-muted-foreground">Start</dt>
          <dd className="data-value">{formatLonLat(mission.startLon, mission.startLat, 5)}</dd>
          <dt className="text-muted-foreground">Destination</dt>
          <dd className="data-value">{formatLonLat(mission.destLon, mission.destLat, 5)}</dd>
          <dt className="text-muted-foreground">Priorities</dt>
          <dd>{PRESET_LABEL[mission.profile]}</dd>
          {mission.objective && (
            <>
              <dt className="text-muted-foreground">Objective</dt>
              <dd>{mission.objective}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Mission id</dt>
          <dd className="data-value">{mission.id}</dd>
        </dl>
      </PopoverContent>
    </Popover>
  );
}

export function MissionHeader({
  id,
  mission,
  actions,
}: {
  id: number;
  mission: Mission | undefined;
  actions?: ReactNode;
}) {
  return (
    <div className="no-print shrink-0 border-b border-border bg-panel">
      <div className="flex items-center gap-3 px-4 pt-2.5">
        <div className="min-w-0 flex-1">
          {mission ? (
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <h1 className="truncate text-base font-semibold tracking-tight">{mission.name}</h1>
              <StatusBadge status={mission.status} />
              <MissionDetails mission={mission} />
            </div>
          ) : (
            <Skeleton className="h-6 w-72" />
          )}
        </div>
        {actions}
      </div>
      <nav className="-mb-px mt-1 flex gap-1 px-2" aria-label="Mission screens">
        {TABS.map((t) => (
          <Link
            key={t.to}
            to={t.to}
            params={{ id: String(id) }}
            className="border-b-2 border-transparent px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground data-[status=active]:border-mars data-[status=active]:text-foreground"
          >
            {t.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
