import { Lock } from "lucide-react";

export function FinalizedBanner() {
  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-status-finalized/40 bg-status-finalized/10 px-5 py-2 text-sm text-status-finalized"
    >
      <Lock className="size-4 shrink-0" />
      This mission is finalized. Editing is disabled; open the report or duplicate it from Missions
      to plan changes.
    </div>
  );
}
