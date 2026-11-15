import { Star } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FeatureType } from "@/types";

/** Small legend glyph matching how each feature type is drawn on the map. */
export function FeatureSwatch({ type, className }: { type: FeatureType; className?: string }) {
  const c = cn("inline-flex shrink-0 items-center justify-center", className);
  switch (type) {
    case "HAZARD":
      return (
        <span className={cn(c, "size-3 rotate-45 rounded-[2px] bg-map-hazard")}>
          <b className="-rotate-45 text-[8px] leading-none text-background">!</b>
        </span>
      );
    case "SCIENCE_TARGET":
      return <Star className={cn(c, "size-3.5 fill-map-science text-map-science")} aria-hidden />;
    case "SAFE_POINT":
      return (
        <span
          className={cn(
            c,
            "size-3.5 rounded-full bg-map-safe font-mono text-[8px] font-bold text-background",
          )}
        >
          S
        </span>
      );
    case "COMMUNICATION_ASSET":
      return (
        <span
          className={cn(
            c,
            "size-3.5 rounded-full bg-map-comms font-mono text-[8px] font-bold text-background",
          )}
        >
          C
        </span>
      );
    case "ROVER_PATH":
      return <span className={cn(c, "rg-legend-rover h-0 w-4")} />;
    case "TERRAIN_UNIT":
      return (
        <span
          className={cn(c, "size-3 rounded-[2px] border border-map-terrain bg-map-terrain/20")}
        />
      );
    case "RIM_SCARP":
      return <span className={cn(c, "rg-legend-rim h-0 w-4")} />;
    case "LANDING_ELLIPSE":
      return <span className={cn(c, "rg-legend-ellipse h-2.5 w-4 rounded-full")} />;
  }
}
