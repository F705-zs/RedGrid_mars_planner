import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { FolderOpen, MoreHorizontal, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useDuplicateMission, useMissions, useSetMissionStatus } from "@/api/queries";
import { StatusBadge } from "@/components/common/badges";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PRESET_LABEL, STATUS_LABEL } from "@/lib/labels";
import { STATUS_TRANSITIONS } from "@/lib/mission-status";
import { useRegionContext } from "@/lib/region-context";
import type { Mission, MissionStatus } from "@/types";
import { MISSION_STATUSES } from "@/types";

export const Route = createFileRoute("/missions/")({
  head: () => ({
    meta: [
      { title: "Missions — RedGrid" },
      {
        name: "description",
        content:
          "All RedGrid Mars missions with status, profile and region. Open, duplicate or advance a mission.",
      },
      { property: "og:title", content: "Missions — RedGrid" },
      { property: "og:description", content: "List of planned Mars missions by status." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: MissionsList,
});

function RowMenu({ mission }: { mission: Mission }) {
  const navigate = useNavigate();
  const duplicate = useDuplicateMission();
  const setStatus = useSetMissionStatus();
  const id = String(mission.id);
  const finalized = mission.status === "FINALIZED";
  const transitions = STATUS_TRANSITIONS[mission.status];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          aria-label={`Actions for ${mission.name}`}
        >
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onSelect={() => navigate({ to: "/missions/$id/routes", params: { id } })}>
          Open
        </DropdownMenuItem>
        {!finalized && (
          <DropdownMenuItem onSelect={() => navigate({ to: "/missions/$id/edit", params: { id } })}>
            Edit
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => navigate({ to: "/missions/$id/report", params: { id } })}>
          Report
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={duplicate.isPending}
          onSelect={() =>
            duplicate.mutate(mission.id, {
              onSuccess: (copy) =>
                toast.success(`Duplicated as "${copy.name}"`, {
                  action: {
                    label: "Open",
                    onClick: () =>
                      navigate({ to: "/missions/$id/routes", params: { id: String(copy.id) } }),
                  },
                }),
            })
          }
        >
          Duplicate
        </DropdownMenuItem>
        {transitions.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuSub>
              <DropdownMenuSubTrigger disabled={setStatus.isPending}>
                Change status
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                {transitions.map((to) => (
                  <DropdownMenuItem
                    key={to}
                    onSelect={() =>
                      setStatus.mutate(
                        { id: mission.id, status: to },
                        {
                          onSuccess: (m) =>
                            toast.success(
                              `${m.name} is now ${STATUS_LABEL[m.status].toLowerCase()}`,
                            ),
                        },
                      )
                    }
                  >
                    <StatusBadge status={to} />
                  </DropdownMenuItem>
                ))}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MissionsList() {
  const [status, setStatus] = useState<MissionStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const missions = useMissions(status === "ALL" ? undefined : status);
  const { regions } = useRegionContext();
  const regionName = (id: number) => regions?.find((r) => r.id === id)?.name ?? `Region ${id}`;
  const showRegion = new Set((missions.data ?? []).map((m) => m.regionId)).size > 1;
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (missions.data ?? []).filter(
      (m) =>
        !q || m.name.toLowerCase().includes(q) || (m.objective ?? "").toLowerCase().includes(q),
    );
  }, [missions.data, search]);
  const cols = showRegion ? 5 : 4;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-6">
      <div className="flex flex-wrap items-center gap-2 pb-4">
        <h1 className="mr-auto text-xl font-semibold tracking-tight">Missions</h1>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search"
            className="h-8 w-48 pl-7"
            aria-label="Search missions"
          />
        </div>
        <Select value={status} onValueChange={(v) => setStatus(v as MissionStatus | "ALL")}>
          <SelectTrigger className="h-8 w-36" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All statuses</SelectItem>
            {MISSION_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABEL[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {missions.error ? (
        <ErrorState error={missions.error} onRetry={() => missions.refetch()} />
      ) : !missions.isLoading && !missions.data?.length ? (
        <EmptyState
          icon={<FolderOpen className="size-5" />}
          title={
            status === "ALL"
              ? "No missions yet"
              : `No ${STATUS_LABEL[status].toLowerCase()} missions`
          }
          description={
            status === "ALL"
              ? "Use New mission above to plan your first walk."
              : "Try another status filter."
          }
        />
      ) : (
        <div className="panel overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead className="w-32">Status</TableHead>
                <TableHead className="w-40">Priorities</TableHead>
                {showRegion && <TableHead className="w-40">Region</TableHead>}
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {missions.isLoading
                ? Array.from({ length: 3 }, (_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: cols }, (_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-24" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : shown.map((m) => (
                    <TableRow key={m.id}>
                      <TableCell className="py-2 font-medium">
                        <Link
                          to="/missions/$id/routes"
                          params={{ id: String(m.id) }}
                          className="hover:underline"
                          title={showRegion ? undefined : regionName(m.regionId)}
                        >
                          {m.name}
                        </Link>
                        {m.objective && (
                          <p className="truncate text-xs font-normal text-muted-foreground">
                            {m.objective}
                          </p>
                        )}
                      </TableCell>
                      <TableCell className="py-2">
                        <StatusBadge status={m.status} />
                      </TableCell>
                      <TableCell className="py-2 text-sm text-muted-foreground">
                        {PRESET_LABEL[m.profile]}
                      </TableCell>
                      {showRegion && (
                        <TableCell className="py-2 text-sm">{regionName(m.regionId)}</TableCell>
                      )}
                      <TableCell className="py-2 text-right">
                        <RowMenu mission={m} />
                      </TableCell>
                    </TableRow>
                  ))}
              {!missions.isLoading && shown.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={cols}
                    className="py-8 text-center text-sm text-muted-foreground"
                  >
                    No missions match “{search}”.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
