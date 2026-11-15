import { ClientOnly } from "@tanstack/react-router";
import { lazy, Suspense } from "react";

import type { MarsMapProps } from "./map-types";

// Leaflet touches `window` at import time, so the map module is loaded only in the browser.
const MarsMap = lazy(() => import("./MarsMap"));

function MapFallback() {
  return (
    <div className="grid-backdrop flex h-full w-full items-center justify-center bg-background">
      <span className="eyebrow animate-pulse">Loading map…</span>
    </div>
  );
}

export function LazyMarsMap(props: MarsMapProps) {
  return (
    <ClientOnly fallback={<MapFallback />}>
      <Suspense fallback={<MapFallback />}>
        <MarsMap {...props} />
      </Suspense>
    </ClientOnly>
  );
}
