import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useRegionContext } from "@/lib/region-context";

/** A static label when the API offers one region; a selector only when several valid regions exist. */
export function RegionSelector() {
  const { regions, region, setRegionId, isLoading } = useRegionContext();
  if (isLoading) return <Skeleton className="h-6 w-28" />;
  if (!region) return null;
  if ((regions?.length ?? 0) <= 1)
    return (
      <span
        className="rounded border border-border px-2 py-0.5 text-xs text-muted-foreground"
        aria-label="Region"
      >
        {region.name}
      </span>
    );
  return (
    <Select value={String(region.id)} onValueChange={(v) => setRegionId(Number(v))}>
      <SelectTrigger
        className="h-7 w-auto gap-2 border-border bg-surface text-xs"
        aria-label="Region"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {regions?.map((r) => (
          <SelectItem key={r.id} value={String(r.id)}>
            {r.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
