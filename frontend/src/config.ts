// App configuration. Values come from Vite env vars (VITE_*) so they can change per deploy.

const env = import.meta.env as Record<string, string | undefined>;

/** Base URL of the RedGrid REST API (API Contract V6). */
export const API_BASE_URL: string = (
  env["VITE_API_BASE_URL"] || "http://localhost:5000/api"
).replace(/\/$/, "");

/**
 * Mock mode answers from src/mocks (isolated test fixtures). OFF by default: the normal application always calls the
 * real API and never falls back to mock data. Set VITE_USE_MOCKS=true only for offline UI development.
 */
export const USE_MOCKS: boolean = (env["VITE_USE_MOCKS"] ?? "false").toLowerCase() === "true";

/**
 * Primary Mars basemap: NASA Mars Trek WMTS, equirectangular (EQ) tile matrix "default028mm", which Leaflet's
 * EPSG:4326 CRS matches (2 x 1 tiles at zoom 0, rows from the north). Layer: Viking MDIM 2.1 colour mosaic, 232 m/px,
 * so native tiles exist up to zoom 7; Leaflet enlarges them beyond that (blurry but correctly placed).
 * The app checks one tile at start-up and falls back to the backend's own imagery if Trek does not answer.
 */
export const MARS_BASE_TILE_URL: string =
  env["VITE_MARS_BASE_TILE_URL"] ??
  "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg";
export const MARS_BASE_MAX_NATIVE_ZOOM: number = Number(env["VITE_MARS_BASE_MAX_NATIVE_ZOOM"] ?? 7);
export const MARS_BASE_ATTRIBUTION = "NASA Mars Trek · Viking MDIM 2.1 (NASA/JPL/USGS)";

/**
 * Backend raster layers used, in order, as real-imagery fallback when Mars Trek is unavailable (dataset registry:
 * Mars 2020 TRN HiRISE orthomosaic, Mars 2020 CTX orthomosaic). Drawn only where the backend has data.
 */
export const IMAGERY_FALLBACK_LAYERS = ["imagery_hirise", "imagery_ctx"] as const;

/** URL of the merged 3D Jezero walk (built into public/mars3d). */
const baseUrl = (env["BASE_URL"] || "/").replace(/\/?$/, "/");
export const MARS3D_URL: string = env["VITE_MARS3D_URL"] || `${baseUrl}mars3d/index.html`;

/** Shown on every page (required wording: human mobility, oxygen, battery, not official NASA EVA limits). */
export const PROTOTYPE_NOTICE =
  "Prototype human-mobility, oxygen and battery assumptions; not official NASA EVA limits.";
