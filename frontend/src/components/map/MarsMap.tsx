// Browser-only react-leaflet map of a Mars region. Loaded lazily via LazyMarsMap.
//
// CRS: Leaflet's EPSG:4326 (geographic lon/lat in degrees, equirectangular) with the
// radius set to Mars so the scale bar and distances are right. Never L.CRS.Simple.
// All [lon, lat] → [lat, lon] conversion goes through toLatLng.

import L from "leaflet";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  GeoJSON,
  ImageOverlay,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Popup,
  Rectangle,
  ScaleControl,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { textureUrl } from "@/api/client";
import {
  IMAGERY_FALLBACK_LAYERS,
  MARS_BASE_ATTRIBUTION,
  MARS_BASE_MAX_NATIVE_ZOOM,
  MARS_BASE_TILE_URL,
} from "@/config";
import { fmtDistance, fmtDuration } from "@/lib/format";
import { circleRing, formatLonLat, fromLatLng, MARS_RADIUS_M, toLatLng } from "@/lib/geo";
import {
  ANNOTATION_LABEL,
  FEATURE_TYPE_LABEL,
  ROUTE_TYPE_CODE,
  ROUTE_TYPE_LABEL,
  SEVERITY_LABEL,
} from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Annotation, Feature, FeatureType, Position, Region } from "@/types";

import type {
  ImageryStatus,
  MapEndpoint,
  MapRouteLine,
  MarsMapProps,
  RasterStatus,
} from "./map-types";

const MARS_CRS = L.extend({}, L.CRS.EPSG4326, { R: MARS_RADIUS_M }) as L.CRS;

const STAR_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z"/></svg>';

function pin(cls: string, html = "", size = 18, tag?: string) {
  return L.divIcon({
    className: "",
    html: `<div class="rg-pin ${cls}">${html}</div>${tag ? `<span class="rg-tag">${tag}</span>` : ""}`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

const FEATURE_ICONS: Partial<Record<FeatureType, () => L.DivIcon>> = {
  HAZARD: () => pin("rg-pin--hazard", "<b>!</b>", 16),
  SCIENCE_TARGET: () => pin("rg-pin--science", STAR_SVG, 22),
  SAFE_POINT: () => pin("rg-pin--safe", "S", 18),
  COMMUNICATION_ASSET: () => pin("rg-pin--comms", "C", 18),
};

const FEATURE_CLASS: Partial<Record<FeatureType, string>> = {
  ROVER_PATH: "rg-feature--rover",
  TERRAIN_UNIT: "rg-feature--terrain",
  RIM_SCARP: "rg-feature--rim",
  LANDING_ELLIPSE: "rg-feature--ellipse",
  HAZARD: "rg-warning-area",
};

function escapeHtml(s: string) {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function featurePopup(f: Feature) {
  const { name, code, featureType, scienceValue, providesRefill, heightM } = f.properties;
  const title = name ?? code ?? FEATURE_TYPE_LABEL[featureType] ?? featureType;
  let html = `<div class="rg-popup-meta">${FEATURE_TYPE_LABEL[featureType] ?? featureType}</div><div class="rg-popup-title">${escapeHtml(title)}</div>`;
  if (featureType === "SCIENCE_TARGET" && scienceValue !== null && scienceValue !== undefined)
    html += `<div>Science value: ${scienceValue}</div>`;
  if (featureType === "SAFE_POINT" && providesRefill !== null && providesRefill !== undefined)
    html += `<div>${providesRefill ? "Refills oxygen and battery" : "Shelter only (no refill)"}</div>`;
  if (featureType === "COMMUNICATION_ASSET" && heightM !== null && heightM !== undefined)
    html += `<div>Antenna height: ${heightM} m</div>`;
  return html;
}

/* ---------- Grid background ---------- */

const STEPS = [0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10];

function Graticule() {
  const map = useMap();
  const [bounds, setBounds] = useState(() => map.getBounds());
  useMapEvents({
    moveend: () => setBounds(map.getBounds()),
    zoomend: () => setBounds(map.getBounds()),
  });

  const west = bounds.getWest();
  const east = bounds.getEast();
  const south = bounds.getSouth();
  const north = bounds.getNorth();
  const span = Math.max(east - west, north - south);
  const step = STEPS.find((s) => span / s <= 5) ?? 10; // few lines and labels: a light navigation aid
  const digits = String(step).split(".")[1]?.length ?? 0;
  const major = step * 5;

  const lons: number[] = [];
  for (let v = Math.ceil(west / step) * step; v <= east; v += step) lons.push(+v.toFixed(6));
  const lats: number[] = [];
  for (let v = Math.ceil(south / step) * step; v <= north; v += step) lats.push(+v.toFixed(6));
  const isMajor = (v: number) => Math.abs(v / major - Math.round(v / major)) < 1e-6;

  return (
    <>
      {lons.map((lon) => (
        <Polyline
          key={`lon${lon}`}
          positions={[toLatLng([lon, south - span]), toLatLng([lon, north + span])]}
          pathOptions={{ className: cn("rg-grid", isMajor(lon) && "rg-grid--major") }}
          interactive={false}
        />
      ))}
      {lats.map((lat) => (
        <Polyline
          key={`lat${lat}`}
          positions={[toLatLng([west - span, lat]), toLatLng([east + span, lat])]}
          pathOptions={{ className: cn("rg-grid", isMajor(lat) && "rg-grid--major") }}
          interactive={false}
        />
      ))}
      {lons.map((lon) => (
        <Marker
          key={`lonl${lon}`}
          position={toLatLng([lon, north])}
          interactive={false}
          keyboard={false}
          icon={L.divIcon({
            className: "rg-grid-label rg-grid-label--lon",
            html: `<span>${lon.toFixed(digits)}°E</span>`,
            iconSize: [0, 0],
          })}
        />
      ))}
      {lats.map((lat) => (
        <Marker
          key={`latl${lat}`}
          position={toLatLng([west, lat])}
          interactive={false}
          keyboard={false}
          icon={L.divIcon({
            className: "rg-grid-label rg-grid-label--lat",
            html: `<span>${lat.toFixed(digits)}°N</span>`,
            iconSize: [0, 0],
          })}
        />
      ))}
    </>
  );
}

/* ---------- Imagery ---------- */

/** Tile x/y of a lon/lat in Leaflet's EPSG:4326 scheme (2 x 1 tiles at zoom 0), which Mars Trek EQ tiles follow. */
function tileXY(lon: number, lat: number, z: number) {
  return {
    x: Math.floor(((lon + 180) / 360) * 2 ** (z + 1)),
    y: Math.floor(((90 - lat) / 180) * 2 ** z),
  };
}

function probeImage(url: string, timeoutMs = 8000): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    const t = window.setTimeout(() => {
      img.src = "";
      resolve(false);
    }, timeoutMs);
    img.onload = () => {
      window.clearTimeout(t);
      resolve(img.naturalWidth > 0);
    };
    img.onerror = () => {
      window.clearTimeout(t);
      resolve(false);
    };
    img.src = url;
  });
}

/**
 * Chooses the real imagery under the map: NASA Mars Trek if one tile over the region loads, else the first backend
 * orthomosaic (HiRISE, then CTX) that the API serves, else none. Never an Earth map or generated terrain.
 */
function useImagery(region: Region, retry: number, onStatus?: (s: ImageryStatus) => void) {
  const [status, setStatus] = useState<ImageryStatus>({ kind: "checking" });
  const report = useRef(onStatus);
  report.current = onStatus;
  useEffect(() => {
    let cancelled = false;
    const set = (s: ImageryStatus) => {
      if (cancelled) return;
      setStatus(s);
      report.current?.(s);
    };
    set({ kind: "checking" });
    void (async () => {
      if (MARS_BASE_TILE_URL) {
        const z = Math.min(MARS_BASE_MAX_NATIVE_ZOOM, 7);
        const { x, y } = tileXY(region.centerLon, region.centerLat, z);
        const url = MARS_BASE_TILE_URL.replace("{z}", String(z))
          .replace("{x}", String(x))
          .replace("{y}", String(y));
        if (await probeImage(url)) return set({ kind: "trek" });
      }
      const d = 0.01;
      const probeBox = {
        west: region.centerLon - d,
        south: region.centerLat - d,
        east: region.centerLon + d,
        north: region.centerLat + d,
      };
      for (const key of IMAGERY_FALLBACK_LAYERS) {
        if (await probeImage(textureUrl(region.id, key, probeBox, 256)))
          return set({ kind: "fallback", layerKey: key });
      }
      set({ kind: "none" });
    })();
    return () => {
      cancelled = true;
    };
  }, [region.id, region.centerLon, region.centerLat, retry]);
  return status;
}

/**
 * A backend RASTER layer drawn as one georeferenced PNG for the current view (clipped to the region), re-requested
 * after the view settles. The image covers exactly its bbox; areas without data are transparent, never stretched.
 */
function ViewportRaster({
  region,
  layerKey,
  opacity,
  onStatus,
}: {
  region: Region;
  layerKey: string;
  opacity: number;
  onStatus?: ((key: string, s: RasterStatus) => void) | undefined;
}) {
  const map = useMap();
  const report = useRef(onStatus);
  report.current = onStatus;
  const compute = () => {
    const b = map.getBounds();
    const west = Math.max(region.bboxWest, b.getWest());
    const east = Math.min(region.bboxEast, b.getEast());
    const south = Math.max(region.bboxSouth, b.getSouth());
    const north = Math.min(region.bboxNorth, b.getNorth());
    if (!(west < east && south < north)) return null;
    const size = map.getSize();
    const frac = Math.max(
      (east - west) / (b.getEast() - b.getWest()),
      (north - south) / (b.getNorth() - b.getSouth()),
    );
    return { bbox: { west, south, east, north }, px: Math.max(size.x, size.y) * frac };
  };
  const [view, setView] = useState(compute);
  const [useStaticFallback, setUseStaticFallback] = useState(
    () => typeof window !== "undefined" && window.location.hostname.endsWith("github.io"),
  );
  const timer = useRef<number | undefined>(undefined);
  useMapEvents({
    moveend: () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setView(compute()), 350);
    },
  });
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => report.current?.(layerKey, "loading"), [layerKey, view, useStaticFallback]);
  if (!view) return null;
  const { bbox, px } = view;
  const baseUrl = import.meta.env.BASE_URL ?? "/";
  const staticUrl = `${baseUrl.endsWith("/") ? baseUrl : baseUrl + "/"}rasters/${layerKey}.png`;
  if (useStaticFallback) {
    return (
      <ImageOverlay
        key={`${layerKey}-static`}
        url={staticUrl}
        bounds={L.latLngBounds(
          toLatLng([region.bboxWest, region.bboxSouth]),
          toLatLng([region.bboxEast, region.bboxNorth]),
        )}
        opacity={opacity}
        interactive={false}
        eventHandlers={{
          load: () => report.current?.(layerKey, "ok"),
          error: () => report.current?.(layerKey, "unavailable"),
        }}
      />
    );
  }
  return (
    <ImageOverlay
      key={`${layerKey}-${bbox.west}-${bbox.south}-${bbox.east}-${bbox.north}`}
      url={textureUrl(region.id, layerKey, bbox, px)}
      bounds={L.latLngBounds(toLatLng([bbox.west, bbox.south]), toLatLng([bbox.east, bbox.north]))}
      opacity={opacity}
      interactive={false}
      eventHandlers={{
        load: () => report.current?.(layerKey, "ok"),
        error: () => setUseStaticFallback(true),
      }}
    />
  );
}

/** Keeps Leaflet's size in step with its container (side panels collapsing or opening). */
function ResizeWatcher() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const ro = new ResizeObserver(() => map.invalidateSize({ debounceMoveend: true }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);
  return null;
}

/* ---------- Behaviour helpers ---------- */

function ClickHandler({ onClick }: { onClick?: ((p: Position) => void) | undefined }) {
  const ref = useRef(onClick);
  ref.current = onClick;
  useMapEvents({ click: (e) => ref.current?.(fromLatLng(e.latlng.lat, e.latlng.lng)) });
  return null;
}

function FitTo({ points }: { points?: Position[] | undefined }) {
  const map = useMap();
  const key = JSON.stringify(points ?? []);
  useEffect(() => {
    if (!points?.length) return;
    if (points.length === 1) map.setView(toLatLng(points[0]!), Math.max(map.getZoom(), 13));
    else map.fitBounds(L.latLngBounds(points.map(toLatLng)), { padding: [70, 70], maxZoom: 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

function CursorReadout() {
  const [pos, setPos] = useState<L.LatLng | null>(null);
  useMapEvents({ mousemove: (e) => setPos(e.latlng), mouseout: () => setPos(null) });
  return (
    <div className="pointer-events-none absolute bottom-2 left-2 z-[1000] rounded border border-border bg-panel/90 px-2 py-1 font-mono text-[10px] text-muted-foreground">
      {pos ? formatLonLat(pos.lng, pos.lat, 4) : "—"}
    </div>
  );
}

/* ---------- Overlays ---------- */

function RouteLines({
  routes,
  onHover,
}: {
  routes: MapRouteLine[];
  onHover?: ((id: number | null) => void) | undefined;
}) {
  return (
    <>
      {routes.map(({ route, highlighted, dimmed }) => {
        const positions = route.geometry.coordinates.map(toLatLng);
        const mid =
          route.geometry.coordinates[Math.floor(route.geometry.coordinates.length * 0.55)];
        const state = `${highlighted ? "h" : ""}${dimmed ? "d" : ""}`;
        const events = { mouseover: () => onHover?.(route.id), mouseout: () => onHover?.(null) };
        return (
          <Fragment key={`${route.id}-${state}`}>
            {highlighted && (
              <Polyline
                positions={positions}
                pathOptions={{ className: "rg-route rg-route--halo" }}
                interactive={false}
              />
            )}
            <Polyline
              positions={positions}
              eventHandlers={events}
              pathOptions={{
                className: cn(
                  "rg-route",
                  `rg-route--${route.routeType}`,
                  !route.feasible && "rg-route--infeasible",
                  highlighted && "is-highlighted",
                  dimmed && "is-dimmed",
                ),
              }}
            >
              <Popup>
                <div className="rg-popup-meta">Route {ROUTE_TYPE_CODE[route.routeType]}</div>
                <div className="rg-popup-title">{ROUTE_TYPE_LABEL[route.routeType]}</div>
                <div>
                  {fmtDistance(route.distanceM)} · {fmtDuration(route.durationMin)}
                  {!route.feasible && " · Not feasible"}
                </div>
              </Popup>
            </Polyline>
            {mid && (
              <Marker
                position={toLatLng(mid)}
                eventHandlers={events}
                icon={pin(
                  cn(
                    "rg-pin--route",
                    `rg-swatch--${route.routeType}`,
                    !route.feasible && "is-infeasible",
                  ),
                  ROUTE_TYPE_CODE[route.routeType],
                  18,
                  route.feasible ? undefined : "Not feasible",
                )}
              />
            )}
          </Fragment>
        );
      })}
    </>
  );
}

function AnnotationMarkers({ annotations }: { annotations: Annotation[] }) {
  return (
    <>
      {annotations.map((a) => (
        <Fragment key={a.id}>
          {a.kind === "HAZARD_WARNING" && a.radiusM ? (
            <Polygon
              positions={circleRing([a.lon, a.lat], a.radiusM).map(toLatLng)}
              pathOptions={{ className: "rg-warning-area" }}
              interactive={false}
            />
          ) : null}
          <Marker
            position={toLatLng([a.lon, a.lat])}
            icon={pin(
              a.kind === "SCIENCE_STOP" ? "rg-pin--stop" : "rg-pin--warning",
              a.kind === "SCIENCE_STOP" ? "S" : "!",
              18,
            )}
          >
            <Popup>
              <div className="rg-popup-meta">{ANNOTATION_LABEL[a.kind]}</div>
              <div className="rg-popup-title">{a.note || "No note"}</div>
              <div>
                {a.kind === "SCIENCE_STOP"
                  ? `Stop: ${fmtDuration(a.durationMin)}`
                  : `${a.severity ? SEVERITY_LABEL[a.severity] : "Unknown"} severity · radius ${fmtDistance(a.radiusM)}`}
              </div>
            </Popup>
          </Marker>
        </Fragment>
      ))}
    </>
  );
}

function EndpointMarker({ endpoint }: { endpoint: MapEndpoint }) {
  const ref = useRef(endpoint.onMove);
  ref.current = endpoint.onMove;
  const handlers = useMemo(
    () => ({
      dragend: (e: L.LeafletEvent) => {
        const ll = (e.target as L.Marker).getLatLng();
        ref.current?.(fromLatLng(ll.lat, ll.lng));
      },
    }),
    [],
  );
  const isStart = endpoint.kind === "start";
  return (
    <Marker
      position={toLatLng(endpoint.position)}
      draggable={!!endpoint.draggable}
      eventHandlers={handlers}
      zIndexOffset={1000}
      title={isStart ? "Start" : "Destination"}
      icon={pin(
        isStart ? "rg-pin--start" : "rg-pin--destination",
        isStart ? "S" : "D",
        24,
        isStart ? "Start" : "Destination",
      )}
    />
  );
}

export default function MarsMap({
  region,
  vectorLayers = [],
  rasterLayers = [],
  routes = [],
  onRouteHover,
  annotations = [],
  draftAnnotation,
  endpoints = [],
  probe,
  onMapClick,
  fitTo,
  className,
  showGrid = false,
  showCursor = false,
  onRasterStatus,
  onImageryStatus,
  imageryRetry = 0,
  footsteps,
}: MarsMapProps) {
  const imagery = useImagery(region, imageryRetry, onImageryStatus);
  const pad = 0.35;
  const maxBounds = L.latLngBounds(
    toLatLng([region.bboxWest - pad, region.bboxSouth - pad]),
    toLatLng([region.bboxEast + pad, region.bboxNorth + pad]),
  );

  return (
    <MapContainer
      crs={MARS_CRS}
      center={toLatLng([region.centerLon, region.centerLat])}
      zoom={region.defaultZoom}
      minZoom={9}
      maxZoom={17}
      maxBounds={maxBounds}
      maxBoundsViscosity={0.8}
      zoomControl={false}
      attributionControl
      className={cn("h-full w-full", onMapClick && "rg-map--pick", className)}
    >
      <svg width="0" height="0" className="absolute" aria-hidden>
        <defs>
          <pattern
            id="rg-hazard-stripes"
            patternUnits="userSpaceOnUse"
            width="10"
            height="10"
            patternTransform="rotate(45)"
          >
            <rect width="10" height="10" className="rg-stripe-bg" />
            <line x1="0" y1="0" x2="0" y2="10" className="rg-stripe-line" strokeWidth="5" />
          </pattern>
        </defs>
      </svg>

      {imagery.kind === "trek" && (
        <TileLayer
          url={MARS_BASE_TILE_URL}
          noWrap
          tileSize={256}
          maxNativeZoom={MARS_BASE_MAX_NATIVE_ZOOM}
          attribution={MARS_BASE_ATTRIBUTION}
        />
      )}
      {imagery.kind === "fallback" && (
        <ViewportRaster region={region} layerKey={imagery.layerKey} opacity={1} />
      )}
      {showGrid && <Graticule />}
      {rasterLayers.map((r) => (
        <ViewportRaster
          key={r.key}
          region={region}
          layerKey={r.key}
          opacity={0.7}
          onStatus={onRasterStatus}
        />
      ))}

      <Rectangle
        bounds={L.latLngBounds(
          toLatLng([region.bboxWest, region.bboxSouth]),
          toLatLng([region.bboxEast, region.bboxNorth]),
        )}
        pathOptions={{ className: "rg-bbox" }}
        interactive={false}
      />
      {region.routableArea && (
        <GeoJSON
          key={`routable-${region.id}`}
          data={region.routableArea as unknown as GeoJSON.GeoJsonObject}
          style={() => ({ className: "rg-routable" })}
          interactive={false}
        />
      )}

      {vectorLayers.map((l) => (
        <GeoJSON
          key={`${l.key}-${l.data.features.length}`}
          data={l.data as unknown as GeoJSON.FeatureCollection}
          style={(f) => ({
            className:
              FEATURE_CLASS[(f as unknown as Feature)?.properties.featureType] ??
              "rg-feature--terrain",
          })}
          pointToLayer={(f, latlng) => {
            const make = FEATURE_ICONS[(f as unknown as Feature).properties.featureType];
            return make
              ? L.marker(latlng, { icon: make() })
              : L.circleMarker(latlng, { radius: 5 });
          }}
          onEachFeature={(f, layer) => layer.bindPopup(featurePopup(f as unknown as Feature))}
        />
      ))}

      {annotations.length > 0 && <AnnotationMarkers annotations={annotations} />}
      {draftAnnotation && (
        <>
          {draftAnnotation.kind === "HAZARD_WARNING" && draftAnnotation.radiusM ? (
            <Polygon
              positions={circleRing(draftAnnotation.position, draftAnnotation.radiusM).map(
                toLatLng,
              )}
              pathOptions={{ className: "rg-warning-area rg-warning-area--draft" }}
              interactive={false}
            />
          ) : null}
          <Marker
            position={toLatLng(draftAnnotation.position)}
            icon={pin("rg-pin--draft", "", 20, "New")}
            interactive={false}
          />
        </>
      )}

      {routes.length > 0 && <RouteLines routes={routes} onHover={onRouteHover} />}
      {endpoints.map((e) => (
        <EndpointMarker key={e.kind} endpoint={e} />
      ))}
      {probe && (
        <Marker
          position={toLatLng(probe)}
          icon={pin("rg-pin--probe", "", 22)}
          interactive={false}
        />
      )}

      {footsteps && footsteps.length > 1 && (
        <Polyline
          positions={footsteps.map(toLatLng)}
          pathOptions={{ className: "rg-footsteps" }}
          interactive={false}
        />
      )}

      <ClickHandler onClick={onMapClick} />
      <FitTo points={fitTo} />
      <ResizeWatcher />
      <ZoomControl position="topright" />
      <ScaleControl position="bottomright" imperial={false} />
      {showCursor && <CursorReadout />}
    </MapContainer>
  );
}
