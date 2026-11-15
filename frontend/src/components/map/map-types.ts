// Browser-safe types for the lazy Leaflet map (no Leaflet imports here).
import type {
  Annotation,
  AnnotationKind,
  FeatureCollection,
  Position,
  Region,
  Route,
} from "@/types";

export interface MapVectorLayer {
  key: string;
  data: FeatureCollection;
}

/** A backend RASTER layer drawn from GET /regions/{id}/terrain/texture for the current view (RedGrid). */
export interface MapRasterLayer {
  key: string;
}

export type RasterStatus = "loading" | "ok" | "unavailable";
/** Which real imagery is under the map: Mars Trek, a backend orthomosaic, or none. */
export type ImageryStatus =
  | { kind: "checking" }
  | { kind: "trek" }
  | { kind: "fallback"; layerKey: string }
  | { kind: "none" };

export interface MapRouteLine {
  route: Route;
  highlighted?: boolean | undefined;
  dimmed?: boolean | undefined;
}

export interface MapEndpoint {
  kind: "start" | "destination";
  position: Position;
  draggable?: boolean | undefined;
  onMove?: ((p: Position) => void) | undefined;
}

export interface MapDraftAnnotation {
  kind: AnnotationKind;
  position: Position;
  radiusM?: number | null | undefined;
}

export interface MarsMapProps {
  region: Region;
  vectorLayers?: MapVectorLayer[] | undefined;
  rasterLayers?: MapRasterLayer[] | undefined;
  routes?: MapRouteLine[] | undefined;
  onRouteHover?: ((routeId: number | null) => void) | undefined;
  annotations?: Annotation[] | undefined;
  draftAnnotation?: MapDraftAnnotation | null | undefined;
  endpoints?: MapEndpoint[] | undefined;
  /** Crosshair marker for the inspected point. */
  probe?: Position | null | undefined;
  onMapClick?: ((p: Position) => void) | undefined;
  /** Fit the view to these points when they change. */
  fitTo?: Position[] | undefined;
  className?: string | undefined;
  /** Optional lon/lat grid (a navigation aid, labelled as a grid, never as imagery). */
  showGrid?: boolean | undefined;
  /** Optional live cursor coordinates. */
  showCursor?: boolean | undefined;
  onRasterStatus?: ((key: string, status: RasterStatus) => void) | undefined;
  onImageryStatus?: ((status: ImageryStatus) => void) | undefined;
  /** Change to re-check imagery sources after a failure. */
  imageryRetry?: number | undefined;
  /** Temporary astronaut footsteps from the 3D walk ([lon, lat] points, session only). */
  footsteps?: Position[] | undefined;
}
