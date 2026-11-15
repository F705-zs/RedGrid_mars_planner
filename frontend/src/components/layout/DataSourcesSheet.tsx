import { Database, ExternalLink } from "lucide-react";

import { useDatasets } from "@/api/queries";
import { EmptyState, ErrorState, PanelSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { USE_MOCKS } from "@/config";
import { fmtDistance, fmtText } from "@/lib/format";
import { useRegionContext } from "@/lib/region-context";
import type { Dataset } from "@/types";

function DatasetCard({ d }: { d: Dataset }) {
  const rows: [string, string][] = [
    ["Provider", d.provider],
    ["Licence", fmtText(d.licence)],
    ["Coverage", fmtText(d.coverage)],
    ["Coordinate system", fmtText(d.coordinateSystem)],
    ["Format", fmtText(d.format)],
    ["Resolution", fmtDistance(d.resolutionM)],
    ["Accessed", fmtText(d.accessedOn)],
    ["DOI", d.doi ?? "No DOI"],
  ];
  return (
    <li className="rounded-lg border border-border bg-surface/40 p-4">
      <p className="text-sm font-medium">{d.name}</p>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="min-w-0 break-words">{v}</dd>
          </div>
        ))}
      </dl>
      {d.url ? (
        <a
          href={d.url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 break-all text-xs text-sand hover:underline"
        >
          {d.url} <ExternalLink className="size-3 shrink-0" />
        </a>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">No public link (team data)</p>
      )}
    </li>
  );
}

export function DataSourcesSheet() {
  const { region } = useRegionContext();
  const datasets = useDatasets(region?.id);
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm">
          <Database />
          Data sources
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto border-border bg-panel sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Data sources</SheetTitle>
          <SheetDescription>
            Datasets behind the layers and values for {region?.name ?? "this region"}.
            {USE_MOCKS && " Mock mode: values come from test fixtures, not the RedGrid API."}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-5">
          {datasets.isLoading ? (
            <div className="space-y-3">
              <PanelSkeleton rows={5} />
              <PanelSkeleton rows={5} />
            </div>
          ) : datasets.error ? (
            <ErrorState error={datasets.error} onRetry={() => datasets.refetch()} />
          ) : !datasets.data?.length ? (
            <EmptyState
              title="No datasets listed"
              description="The API returned no datasets for this region."
            />
          ) : (
            <ul className="space-y-3">
              {datasets.data.map((d) => (
                <DatasetCard key={d.id} d={d} />
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
