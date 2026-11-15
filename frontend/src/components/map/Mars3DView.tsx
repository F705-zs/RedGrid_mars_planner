import { AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MARS3D_URL } from "@/config";
import type { Position } from "@/types";
import { sceneToLonLat } from "@/lib/footsteps";

/**
 * The merged 3D Jezero walk (the original three.js app, unchanged apart from base-path asset loading and one
 * position message). It runs in an isolated frame so its global styles, element ids and render loop cannot interfere
 * with the 2D app. Mounted the first time 3D is opened and then kept, so switching views does not restart the scene.
 */
export function Mars3DView({
  visible,
  onStep,
}: {
  visible: boolean;
  onStep: (p: Position) => void;
}) {
  const [opened, setOpened] = useState(visible);
  const [available, setAvailable] = useState<boolean | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const report = useRef(onStep);
  report.current = onStep;

  useEffect(() => {
    if (visible) setOpened(true);
  }, [visible]);

  // Check once that the 3D build is present (it is built separately: `bun run build:3d`)
  useEffect(() => {
    if (!opened || available !== null) return;
    fetch(MARS3D_URL, { method: "GET" })
      .then((r) => setAvailable(r.ok))
      .catch(() => setAvailable(false));
  }, [opened, available]);

  // Astronaut positions from the 3D walk: accepted only from the frame itself
  useEffect(() => {
    const origin = new URL(MARS3D_URL, window.location.href).origin;
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== origin || e.source !== frame.current?.contentWindow) return;
      const d = e.data as { type?: string; east?: number; north?: number };
      if (d?.type === "redgrid:walk" && Number.isFinite(d.east) && Number.isFinite(d.north))
        report.current(sceneToLonLat(d.east as number, d.north as number));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (visible) frame.current?.focus();
  }, [visible]);

  if (!opened) return null;
  return (
    <div
      className="absolute inset-0 z-[1050] bg-background"
      style={{ display: visible ? "block" : "none" }}
    >
      {available === false ? (
        <div className="flex h-full items-center justify-center p-6">
          <div className="max-w-md text-center text-sm">
            <AlertCircle className="mx-auto mb-2 size-6 text-destructive" />
            <p className="font-medium">3D view not available</p>
            <p className="mt-1 text-muted-foreground">
              The 3D Jezero walk has not been built into this site. Run{" "}
              <code className="data-value">bun run build:3d</code>, or set VITE_MARS3D_URL to where
              it is hosted.
            </p>
          </div>
        </div>
      ) : available === null ? (
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
          <Loader2 className="mr-2 size-4 animate-spin" /> Loading 3D view…
        </div>
      ) : (
        <iframe
          ref={frame}
          src={MARS3D_URL}
          title="3D view of Jezero Crater: walk the astronaut with W A S D"
          className="h-full w-full border-0"
          allow="fullscreen; autoplay"
        />
      )}
    </div>
  );
}
