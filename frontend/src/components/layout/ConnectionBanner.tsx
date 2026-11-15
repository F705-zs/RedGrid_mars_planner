import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, WifiOff } from "lucide-react";

import { isApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/config";
import { useRegionContext } from "@/lib/region-context";

/**
 * Shown when the RedGrid API cannot be reached. Nothing is invented in the meantime: loaded data stays on screen,
 * missing data stays missing, and Retry refetches every query.
 */
export function ConnectionBanner() {
  const { error } = useRegionContext();
  const qc = useQueryClient();
  if (!isApiError(error, "NETWORK_ERROR")) return null;
  return (
    <div
      role="alert"
      className="no-print flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-1.5 text-sm"
    >
      <WifiOff className="size-4 shrink-0 text-destructive" aria-hidden />
      <span className="min-w-0 flex-1">
        Cannot reach the RedGrid API at <span className="data-value">{API_BASE_URL}</span>. No data
        is shown until it answers.
      </span>
      <Button size="sm" variant="outline" className="h-7" onClick={() => void qc.refetchQueries()}>
        <RefreshCw /> Retry
      </Button>
    </div>
  );
}
