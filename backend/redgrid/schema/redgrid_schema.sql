-- RedGrid database schema (SQLite 3.25 or newer)
-- Changes from V5:
--   * Provider contracts: routes record which cost provider and priority resolver produced them
--     (cost_model_id is now required only when the ALGORITHM provider answered).
--   * Routable area: region.routable_geometry_json (full-data HiRISE coverage). Routing never leaves it.
--   * Custom priority mix: priority_preset (preset weight sets) + mission_priority_mix.
--   * Terrain class: terrain_class_mapping (SIM 3464 unit -> generic class), TerrainClass values.
--   * Demo time window: demo_window (latest 30 sols of MEDA); environmental_snapshot averages over it.
--   * Categories: slope_15_20 added (max slope now 20 deg); near_rover_path moves to the new ROVER_PATH group;
--     every distance and threshold is a planning constant.
--   * Physics-based cost: walking energy from Minetti et al. (2002) and terrain factors from Pandolf/Soule-Goldman;
--     slope and terrain category weights are 1 in version 0 (physics is in the base cost); every other
--     hand-set number is marked PLACEHOLDER (category_weight.basis, priority_preset.basis).
--   * route_profile.return_budget_fraction removed: the physical return limit replaces it.
--   * Feature types: RADIATION_ZONE removed (future work); RIM_SCARP and LANDING_ELLIPSE added;
--     feature.code and feature.height_m added.
--   * Mission: objective (optional text).
--   * Seed data: region, datasets, layers, demonstration points, presets, mapping, constants.
-- Requires SQLite 3.38+ (built-in JSON functions; window functions 3.25+; partial indexes 3.8+).
-- Enumerations are stored as their uppercase names, checked against the allowed list.

PRAGMA foreign_keys = ON;

-- =====================================================================
-- Catalog
-- =====================================================================
CREATE TABLE region (
  id                     INTEGER PRIMARY KEY,
  name                   TEXT NOT NULL,
  bbox_west              REAL NOT NULL,
  bbox_south             REAL NOT NULL,
  bbox_east              REAL NOT NULL,
  bbox_north             REAL NOT NULL,
  coordinate_system      TEXT NOT NULL,
  center_lon             REAL NOT NULL,
  center_lat             REAL NOT NULL,
  default_zoom           INTEGER NOT NULL,
  -- polygon (GeoJSON Polygon or MultiPolygon) where every routing layer has full data.
  -- Written by the data-preparation tool. NULL = data not prepared yet: routing is refused.
  routable_geometry_json TEXT CHECK (routable_geometry_json IS NULL OR json_valid(routable_geometry_json)),
  CHECK (bbox_west < bbox_east AND bbox_south < bbox_north)
);

CREATE TABLE dataset (
  id                INTEGER PRIMARY KEY,
  name              TEXT NOT NULL,
  provider          TEXT NOT NULL,
  doi               TEXT,
  url               TEXT,
  licence           TEXT,
  coverage          TEXT,
  coordinate_system TEXT,
  format            TEXT,
  resolution_m      REAL,
  accessed_on       DATE,          -- YYYY-MM-DD
  is_training       INTEGER NOT NULL DEFAULT 0 CHECK (is_training IN (0,1))   -- used only by the model team
);

CREATE TABLE layer (
  id           INTEGER PRIMARY KEY,
  region_id    INTEGER NOT NULL REFERENCES region(id),
  dataset_id   INTEGER NOT NULL REFERENCES dataset(id),
  key          TEXT NOT NULL,
  display_name TEXT NOT NULL,
  kind         TEXT NOT NULL CHECK (kind IN ('VECTOR','RASTER')),
  data_state   TEXT NOT NULL CHECK (data_state IN ('LATEST_OBSERVATION','HISTORICAL_OBSERVATION','MODELLED_CONDITION','DEMONSTRATION_DATA','DATA_UNAVAILABLE','LIMITED_CONFIDENCE','DERIVED')),
  default_on   INTEGER NOT NULL DEFAULT 0 CHECK (default_on IN (0,1)),
  raster_path  TEXT,             -- relative to DATA_DIR; RASTER layers only
  UNIQUE (region_id, key),
  CHECK ((kind = 'RASTER') = (raster_path IS NOT NULL))
);

CREATE TABLE feature (
  id              INTEGER PRIMARY KEY,
  layer_id        INTEGER NOT NULL REFERENCES layer(id),
  feature_type    TEXT NOT NULL CHECK (feature_type IN ('HAZARD','RIM_SCARP','SCIENCE_TARGET','SAFE_POINT','COMMUNICATION_ASSET','ROVER_PATH','TERRAIN_UNIT','LANDING_ELLIPSE')),
  name            TEXT,
  code            TEXT,          -- geology unit symbol, sample name, waypoint id
  geometry_json   TEXT NOT NULL CHECK (json_valid(geometry_json)),
  science_value   REAL CHECK (science_value IS NULL OR (science_value >= 0 AND science_value <= 1)),
  provides_refill INTEGER NOT NULL DEFAULT 0 CHECK (provides_refill IN (0,1)),
  height_m        REAL CHECK (height_m IS NULL OR height_m >= 0),   -- antenna height above ground
  CHECK (provides_refill = 0 OR feature_type = 'SAFE_POINT'),
  CHECK (science_value IS NULL OR feature_type = 'SCIENCE_TARGET'),
  CHECK (height_m IS NULL OR feature_type = 'COMMUNICATION_ASSET')
);
CREATE INDEX feature_by_layer ON feature(layer_id, feature_type);

-- SIM 3464 geology unit -> generic terrain class (accepted by the team, 14 Nov 2026)
CREATE TABLE terrain_class_mapping (
  unit_symbol   TEXT PRIMARY KEY,               -- SIM 3464 'symbol' field (subscript included)
  unit_name     TEXT NOT NULL,                  -- SIM 3464 'name' field, spelling as published
  terrain_class TEXT NOT NULL CHECK (terrain_class IN ('REGOLITH','BEDROCK','SAND','BOULDER_FIELD')),
  dataset_id    INTEGER NOT NULL REFERENCES dataset(id),
  reason        TEXT NOT NULL
);

-- =====================================================================
-- Environment and the demo time window
-- =====================================================================
-- one row. Every time-dependent value (weather, dust, season, rover path end, default
-- mission start) is taken from this window so the whole demo is coherent.
CREATE TABLE demo_window (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  start_sol        INTEGER NOT NULL,
  end_sol          INTEGER NOT NULL,
  start_utc        TIMESTAMP NOT NULL,
  end_utc          TIMESTAMP NOT NULL,
  solar_longitude_start REAL CHECK (solar_longitude_start IS NULL OR (solar_longitude_start >= 0 AND solar_longitude_start < 360)),
  solar_longitude_end   REAL CHECK (solar_longitude_end   IS NULL OR (solar_longitude_end   >= 0 AND solar_longitude_end   < 360)),
  source           TEXT NOT NULL,
  data_state       TEXT NOT NULL CHECK (data_state IN ('LATEST_OBSERVATION','HISTORICAL_OBSERVATION','MODELLED_CONDITION','DEMONSTRATION_DATA','DATA_UNAVAILABLE','LIMITED_CONFIDENCE','DERIVED')),
  CHECK (end_sol >= start_sol AND end_sol - start_sol < 30)   -- at most 30 sols
);

CREATE TABLE environmental_observation (
  id              INTEGER PRIMARY KEY,
  region_id       INTEGER NOT NULL REFERENCES region(id),
  sol             INTEGER,
  measurement_lon REAL,
  measurement_lat REAL,
  observed_at     TIMESTAMP NOT NULL,      -- YYYY-MM-DDTHH:MM:SSZ
  variable        TEXT NOT NULL CHECK (variable IN ('temperature','pressure','wind_speed','dust_opacity')),
  unit            TEXT,
  value           REAL,
  source          TEXT,
  data_state      TEXT NOT NULL CHECK (data_state IN ('LATEST_OBSERVATION','HISTORICAL_OBSERVATION','MODELLED_CONDITION','DEMONSTRATION_DATA','DATA_UNAVAILABLE','LIMITED_CONFIDENCE','DERIVED'))
);
CREATE INDEX observation_by_region_sol ON environmental_observation(region_id, variable, sol);

-- means over the demo window (not the single newest reading)
CREATE VIEW environmental_snapshot AS
SELECT r.id AS region_id,
  (SELECT AVG(o.value) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.variable = 'temperature'  AND o.sol BETWEEN w.start_sol AND w.end_sol) AS temperature,
  (SELECT AVG(o.value) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.variable = 'pressure'     AND o.sol BETWEEN w.start_sol AND w.end_sol) AS pressure,
  (SELECT AVG(o.value) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.variable = 'wind_speed'   AND o.sol BETWEEN w.start_sol AND w.end_sol) AS wind_speed,
  (SELECT AVG(o.value) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.variable = 'dust_opacity' AND o.sol BETWEEN w.start_sol AND w.end_sol) AS dust_opacity,
  (SELECT COUNT(DISTINCT o.sol) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.sol BETWEEN w.start_sol AND w.end_sol) AS sols_with_data,
  (SELECT w.start_sol FROM demo_window w) AS window_start_sol,
  (SELECT w.end_sol   FROM demo_window w) AS window_end_sol,
  (SELECT MAX(o.observed_at) FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.sol BETWEEN w.start_sol AND w.end_sol) AS observed_at,
  (SELECT o.source     FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.sol BETWEEN w.start_sol AND w.end_sol ORDER BY o.observed_at DESC LIMIT 1) AS source,
  (SELECT o.data_state FROM environmental_observation o, demo_window w WHERE o.region_id = r.id AND o.sol BETWEEN w.start_sol AND w.end_sol ORDER BY o.observed_at DESC LIMIT 1) AS data_state
FROM region r;

-- =====================================================================
-- Planning constants: every threshold, distance and default, with its source
-- =====================================================================
CREATE TABLE planning_constant (
  key         TEXT PRIMARY KEY,
  value       REAL NOT NULL,
  unit        TEXT NOT NULL,
  description TEXT NOT NULL,
  source      TEXT NOT NULL,
  data_state  TEXT NOT NULL CHECK (data_state IN ('LATEST_OBSERVATION','HISTORICAL_OBSERVATION','MODELLED_CONDITION','DEMONSTRATION_DATA','DATA_UNAVAILABLE','LIMITED_CONFIDENCE','DERIVED'))
);

-- =====================================================================
-- Cost weights (used by the ALGORITHM cost provider; written by the training package)
-- =====================================================================
CREATE TABLE category (
  key            TEXT PRIMARY KEY,
  display_name   TEXT NOT NULL,
  category_group TEXT NOT NULL CHECK (category_group IN ('HAZARD','TERRAIN','SCIENCE','COMMUNICATION','UNCERTAINTY','ROVER_PATH')),
  scope          TEXT NOT NULL CHECK (scope IN ('SHARED','HUMAN_ONLY','FIXED')),
  layer_key      TEXT NOT NULL,          -- which layer the category is read from ('*' = any required layer)
  rule           TEXT NOT NULL,          -- how it is measured; thresholds named after planning constants
  is_reference   INTEGER NOT NULL DEFAULT 0 CHECK (is_reference IN (0,1)),
  bit            INTEGER NOT NULL UNIQUE CHECK (bit BETWEEN 0 AND 31)   -- bit in the CostRequest category grid
);

CREATE TABLE cost_model (
  id               INTEGER PRIMARY KEY,
  version          INTEGER NOT NULL UNIQUE,
  method           TEXT NOT NULL CHECK (method IN ('HAND_SET','CONDITIONAL_LOGIT')),
  status           TEXT NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  trained_on       DATE,
  training_summary TEXT,
  test_score       REAL CHECK (test_score IS NULL OR (test_score >= 0 AND test_score <= 1)),
  created_at       TIMESTAMP NOT NULL
);
CREATE UNIQUE INDEX one_active_cost_model ON cost_model(status) WHERE status = 'ACTIVE';

CREATE TABLE category_weight (
  model_id     INTEGER NOT NULL REFERENCES cost_model(id),
  category_key TEXT NOT NULL REFERENCES category(key),
  coefficient  REAL,
  weight       REAL NOT NULL CHECK (weight > 0),
  probability  REAL CHECK (probability IS NULL OR (probability >= 0 AND probability <= 1)),
  std_error    REAL,
  -- where the number comes from. REFERENCE = baseline (always 1); PHYSICS_IN_BASE = 1 because the effect is
  -- already in the physics-based base cost; PLACEHOLDER = hand-set until a learned version replaces it; LEARNED = model.
  basis        TEXT NOT NULL CHECK (basis IN ('REFERENCE','PHYSICS_IN_BASE','PLACEHOLDER','LEARNED')),
  CHECK (basis <> 'REFERENCE' OR weight = 1),
  CHECK (basis <> 'PHYSICS_IN_BASE' OR weight = 1),
  PRIMARY KEY (model_id, category_key)
);

CREATE TABLE training_dataset_link (
  model_id   INTEGER NOT NULL REFERENCES cost_model(id),
  dataset_id INTEGER NOT NULL REFERENCES dataset(id),
  PRIMARY KEY (model_id, dataset_id)
);

CREATE TABLE training_route (
  id            INTEGER PRIMARY KEY,
  dataset_id    INTEGER NOT NULL REFERENCES dataset(id),
  agent_type    TEXT NOT NULL CHECK (agent_type IN ('HUMAN','ROVER')),
  body          TEXT NOT NULL CHECK (body IN ('MARS','MOON')),
  name          TEXT NOT NULL,
  geometry_json TEXT NOT NULL CHECK (json_valid(geometry_json)),
  kept_aside    INTEGER NOT NULL DEFAULT 0 CHECK (kept_aside IN (0,1))
);

-- =====================================================================
-- Route profiles and their limits
-- =====================================================================
CREATE TABLE route_profile (
  key                    TEXT PRIMARY KEY CHECK (key IN ('SAFEST','SHORTEST','SCIENCE_FOCUSED','MISSION_PRIORITY')),
  display_name           TEXT NOT NULL,
  -- 1 = base cost is distance, 0 = base cost is the share of oxygen and battery used. RedGrid: NULL = from the
  -- priority resolver (MISSION_PRIORITY). return_budget_fraction was removed in RedGrid: the physical return limit replaces it.
  distance_weight        REAL CHECK (distance_weight IS NULL OR distance_weight BETWEEN 0 AND 1),
  CHECK ((key = 'MISSION_PRIORITY') = (distance_weight IS NULL))
);

CREATE TABLE profile_rule (
  route_type     TEXT NOT NULL REFERENCES route_profile(key),
  category_group TEXT NOT NULL CHECK (category_group IN ('HAZARD','TERRAIN','SCIENCE','COMMUNICATION','UNCERTAINTY','ROVER_PATH')),
  scale          REAL CHECK (scale IS NULL OR scale >= 0),       -- NULL = from the priority resolver
  max_factor     REAL NOT NULL CHECK (max_factor >= 1),           -- cap on the GROUP factor of one square
  max_vs_hazard  REAL CHECK (max_vs_hazard IS NULL OR (max_vs_hazard > 0 AND max_vs_hazard <= 1)),
  PRIMARY KEY (route_type, category_group),
  CHECK (max_vs_hazard IS NULL OR category_group = 'SCIENCE'),
  CHECK (category_group <> 'UNCERTAINTY' OR scale IS NULL OR scale >= 1)
);

-- the weight set behind each preset, used to build a custom mix
CREATE TABLE priority_preset (
  key                       TEXT PRIMARY KEY CHECK (key IN ('BALANCED','SAFETY_FOCUSED','SCIENCE_FOCUSED','SHORTEST')),
  display_name              TEXT NOT NULL,
  description               TEXT NOT NULL,
  safety_weight             REAL NOT NULL CHECK (safety_weight >= 0),
  science_weight            REAL NOT NULL CHECK (science_weight >= 0),
  distance_weight           REAL NOT NULL CHECK (distance_weight >= 0),
  walking_difficulty_weight REAL NOT NULL CHECK (walking_difficulty_weight >= 0),
  return_weight             REAL NOT NULL CHECK (return_weight >= 0),
  environment_weight        REAL NOT NULL CHECK (environment_weight >= 0),
  rover_path_weight         REAL NOT NULL CHECK (rover_path_weight >= 0),
  basis                     TEXT NOT NULL,   -- e.g. PLACEHOLDER until derived by AHP from team pairwise comparisons
  CHECK (abs(safety_weight + science_weight + distance_weight + walking_difficulty_weight
             + return_weight + environment_weight + rover_path_weight - 1.0) < 0.0001)
);

-- =====================================================================
-- Missions
-- =====================================================================
CREATE TABLE mission (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,   -- ids are never reused
  region_id         INTEGER NOT NULL REFERENCES region(id),
  name              TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80),
  objective         TEXT CHECK (objective IS NULL OR length(objective) <= 500),   -- free text, not used in calculations
  start_lon         REAL NOT NULL,
  start_lat         REAL NOT NULL,
  dest_lon          REAL NOT NULL,
  dest_lat          REAL NOT NULL,
  profile           TEXT NOT NULL CHECK (profile IN ('BALANCED','SAFETY_FOCUSED','SCIENCE_FOCUSED','SHORTEST','CUSTOM')),
  status            TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PLANNED','FINALIZED')),
  selected_route_id INTEGER REFERENCES route(id) ON DELETE SET NULL,
  reserve_fraction  REAL NOT NULL DEFAULT 0.2 CHECK (reserve_fraction >= 0 AND reserve_fraction < 1),
  start_is_base     INTEGER NOT NULL DEFAULT 1 CHECK (start_is_base IN (0,1)),
  created_at        TIMESTAMP NOT NULL
);

-- The final seven weights the mission uses (after any mix and fine-tuning), normalised to sum to 1
CREATE TABLE mission_priority_profile (
  mission_id                INTEGER PRIMARY KEY REFERENCES mission(id) ON DELETE CASCADE,
  safety_weight             REAL NOT NULL CHECK (safety_weight >= 0),
  science_weight            REAL NOT NULL CHECK (science_weight >= 0),
  distance_weight           REAL NOT NULL CHECK (distance_weight >= 0),
  walking_difficulty_weight REAL NOT NULL CHECK (walking_difficulty_weight >= 0),
  return_weight             REAL NOT NULL CHECK (return_weight >= 0),
  environment_weight        REAL NOT NULL CHECK (environment_weight >= 0),
  rover_path_weight         REAL NOT NULL CHECK (rover_path_weight >= 0)
);

-- how a CUSTOM mission's weights were built (percent per preset; the service checks they sum to 100)
CREATE TABLE mission_priority_mix (
  mission_id INTEGER NOT NULL REFERENCES mission(id) ON DELETE CASCADE,
  preset_key TEXT NOT NULL REFERENCES priority_preset(key),
  percent    REAL NOT NULL CHECK (percent > 0 AND percent <= 100),
  PRIMARY KEY (mission_id, preset_key)
);

CREATE TABLE annotation (
  id           INTEGER PRIMARY KEY,
  mission_id   INTEGER NOT NULL REFERENCES mission(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN ('SCIENCE_STOP','HAZARD_WARNING')),
  lon          REAL NOT NULL,
  lat          REAL NOT NULL,
  duration_min REAL CHECK (duration_min IS NULL OR duration_min > 0),
  radius_m     REAL CHECK (radius_m IS NULL OR radius_m > 0),
  note         TEXT,
  severity     TEXT CHECK (severity IS NULL OR severity IN ('LOW','MEDIUM','HIGH')),
  CHECK ((kind = 'SCIENCE_STOP'   AND severity IS NULL AND radius_m IS NULL) OR
         (kind = 'HAZARD_WARNING' AND severity IS NOT NULL AND radius_m IS NOT NULL AND duration_min IS NULL))
);

-- Oxygen, battery and work-rate values. USER_INPUT rows come from the user; SENSOR rows from a
-- sensor ResourceProvider (future work); defaults are never stored, they come from planning_constant.
CREATE TABLE resource_reading (
  id          INTEGER PRIMARY KEY,
  mission_id  INTEGER NOT NULL REFERENCES mission(id) ON DELETE CASCADE,
  variable    TEXT NOT NULL CHECK (variable IN ('OXYGEN_KG','BATTERY_WH','METABOLIC_RATE_W','SUIT_POWER_W')),
  value       REAL NOT NULL CHECK (value >= 0),
  unit        TEXT NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('USER_INPUT','SENSOR')),
  data_state  TEXT NOT NULL CHECK (data_state IN ('LATEST_OBSERVATION','HISTORICAL_OBSERVATION','MODELLED_CONDITION','DEMONSTRATION_DATA','DATA_UNAVAILABLE','LIMITED_CONFIDENCE','DERIVED'))
);

-- Newest USER_INPUT wins, then newest SENSOR. Variables with no row fall back to the defaults provider.
CREATE VIEW resource_current AS
SELECT mission_id, variable, value, unit, observed_at, source, data_state
FROM (
  SELECT r.*,
         ROW_NUMBER() OVER (
           PARTITION BY r.mission_id, r.variable
           ORDER BY CASE r.source WHEN 'USER_INPUT' THEN 1 ELSE 2 END,
                    r.observed_at DESC, r.id DESC) AS rn   -- id breaks ties: two values in the same second
  FROM resource_reading r
)
WHERE rn = 1;

-- =====================================================================
-- Routes
-- =====================================================================
CREATE TABLE route (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,   -- ids change on every recalculation
  mission_id               INTEGER NOT NULL REFERENCES mission(id) ON DELETE CASCADE,
  route_type               TEXT NOT NULL REFERENCES route_profile(key),
  geometry_json            TEXT NOT NULL CHECK (json_valid(geometry_json)),   -- LineString, [lon, lat, elevationM]
  elevation_profile_json   TEXT CHECK (elevation_profile_json IS NULL OR json_valid(elevation_profile_json)),
  feasible                 INTEGER NOT NULL CHECK (feasible IN (0,1)),
  overall_risk             TEXT NOT NULL CHECK (overall_risk IN ('LOW','MODERATE','HIGH','CRITICAL')),
  mission_match            REAL CHECK (mission_match BETWEEN 0 AND 100),
  distance_m               REAL,
  duration_min             REAL,
  average_slope_deg        REAL,
  max_slope_deg            REAL,
  elevation_gain_m         REAL,
  elevation_loss_m         REAL,
  terrain_difficulty       REAL,
  science_score            REAL,
  hazard_count             INTEGER,
  recommendation           TEXT,
  oxygen_used_kg           REAL,
  battery_used_wh          REAL,
  oxygen_left_kg           REAL,
  battery_left_wh          REAL,
  -- who produced the costs and the priority scales
  cost_model_id            INTEGER REFERENCES cost_model(id),
  cost_provider            TEXT NOT NULL,
  cost_provider_kind       TEXT NOT NULL CHECK (cost_provider_kind IN ('ALGORITHM','MODEL')),
  cost_provider_transport  TEXT NOT NULL CHECK (cost_provider_transport IN ('LOCAL','HTTP')),
  cost_provider_version    TEXT NOT NULL,
  priority_resolver        TEXT NOT NULL,
  priority_resolver_kind   TEXT NOT NULL CHECK (priority_resolver_kind IN ('ALGORITHM','MODEL')),
  priority_resolver_version TEXT NOT NULL,
  window_json              TEXT CHECK (window_json IS NULL OR json_valid(window_json)),   -- corridor bbox used
  calculated_at            TIMESTAMP NOT NULL,
  CHECK (cost_provider_kind = 'MODEL' OR cost_model_id IS NOT NULL)
);
CREATE INDEX route_by_mission ON route(mission_id);

CREATE TABLE route_assessment (
  route_id             INTEGER PRIMARY KEY REFERENCES route(id) ON DELETE CASCADE,
  dust_status          TEXT,
  communication_status TEXT,
  data_confidence      REAL CHECK (data_confidence IS NULL OR (data_confidence >= 0 AND data_confidence <= 1))
);

CREATE TABLE return_feasibility (
  route_id                  INTEGER PRIMARY KEY REFERENCES route(id) ON DELETE CASCADE,
  feasible                  INTEGER NOT NULL CHECK (feasible IN (0,1)),
  distance_to_safe_point_m  REAL,
  return_duration_min       REAL,
  maximum_return_distance_m REAL,
  safe_point_name           TEXT,
  reason                    TEXT,
  limiting_resource         TEXT NOT NULL DEFAULT 'NONE' CHECK (limiting_resource IN ('OXYGEN','BATTERY','TIME','NONE')),
  refill_point_name         TEXT
);

CREATE TABLE route_warning (
  id       INTEGER PRIMARY KEY,
  route_id INTEGER NOT NULL REFERENCES route(id) ON DELETE CASCADE,
  message  TEXT NOT NULL
);

-- =====================================================================
-- Seed data
-- =====================================================================

-- Region (official limits)
INSERT INTO region (id, name, bbox_west, bbox_south, bbox_east, bbox_north, coordinate_system,
                    center_lon, center_lat, default_zoom, routable_geometry_json) VALUES
  (1, 'Jezero Crater', 77.20, 18.20, 77.70, 18.70, 'Mars 2000 geographic (east-positive)', 77.45, 18.44, 12, NULL);

-- Datasets (links checked 14 Nov 2026 unless the note says otherwise)
INSERT INTO dataset (id, name, provider, doi, url, licence, coverage, coordinate_system, format, resolution_m, accessed_on, is_training) VALUES
  (1,  'Mars 2020 TRN HiRISE DTM mosaic, 1 m', 'USGS Astrogeology', '10.5066/P9REJ9JN',
       'https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif',
       'Public domain', 'Jezero crater (part)', 'Mars 2000 equirectangular', 'GeoTIFF', 1.0, '2026-11-14', 0),
  (2,  'Mars 2020 TRN HiRISE orthomosaic, 25 cm', 'USGS Astrogeology', NULL,
       'https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif',
       'Public domain', 'Jezero crater (part)', 'Mars 2000 equirectangular', 'GeoTIFF', 0.25, '2026-11-14', 0),
  (3,  'Mars 2020 science investigation CTX DEM, 20 m', 'USGS Astrogeology / JPL', NULL,
       'https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif',
       'Public domain', 'Jezero crater', 'Mars 2000 equirectangular', 'GeoTIFF', 20.0, '2026-11-14', 0),
  (4,  'Mars 2020 science investigation CTX orthomosaic, 5 m', 'USGS Astrogeology / JPL', NULL,
       'https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXortho_mosaic_5m.tif',
       'Public domain', 'Jezero crater', 'Mars 2000 equirectangular', 'GeoTIFF', 5.0, '2026-11-14', 0),
  (5,  'Geologic map of Jezero crater and the Nili Planum region, SIM 3464 (Sun and Stack, 2020)', 'USGS', '10.3133/sim3464',
       'https://pubs.usgs.gov/sim/3464/sim3464_database.zip',
       'Public domain', '76.8-77.8 E, 17.7-18.7 N; 1:75,000', 'Mars 2000 sphere, transverse Mercator (CM 77.5 E)', 'Esri file geodatabase', NULL, '2026-11-14', 0),
  (6,  'THEMIS quantitative thermal inertia mosaic, 100 m, tile 00N060E (Fergason)', 'USGS Astrogeology / ASU', NULL,
       'https://asc-astropedia.s3.us-west-2.amazonaws.com/Mars/Odyssey/THEMIS-Global-Thermal-Inertia-Mosaic/Quantitative-32-Bit/THEMIS_TI_Mosaic_Quant_00N060E_100mpp.cub',
       'Public domain', '0-30 N, 60-90 E', 'Mars 2000', 'ISIS3 cube', 100.0, '2026-11-14', 0),
  (7,  'Mars 2020 traverse (MMGIS)', 'NASA/JPL', NULL,
       'https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json',
       'Public (NASA)', 'Perseverance traverse', 'Mars 2000 geographic', 'GeoJSON', NULL, '2026-11-14', 0),
  (8,  'Mars 2020 MEDA environmental data', 'NASA PDS Atmospheres Node', NULL,
       'https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda',
       'Public (NASA PDS)', 'Jezero crater, demo window', NULL, 'PDS4 tables', NULL, NULL, 0),
  (9,  'NASA Mars Trek base map tiles', 'NASA', NULL,
       'https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars',
       'Public (NASA)', 'Global', 'Mars 2000 equirectangular', 'WMTS tiles', 232.0, '2026-11-14', 0),
  (10, 'Mars 2020 waypoints (MMGIS) - sample sites', 'NASA/JPL', NULL,
       'https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json',
       'Public (NASA)', 'Perseverance waypoints', 'Mars 2000 geographic', 'GeoJSON', NULL, NULL, 0),
  (11, 'RedGrid demonstration points (base, comms tower)', 'RedGrid team', NULL, NULL,
       'Team data', 'Landing site', 'Mars 2000 geographic', 'Database rows', NULL, '2026-11-14', 0),
  (12, 'Apollo 14 traverse mapping dataset (LROC)', 'LROC / ASU', NULL,
       'https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/APOLLO_14/APOLLO_14.ZIP',
       'Public (NASA PDS)', 'Apollo 14 landing site', 'Moon', 'Shapefiles', NULL, '2026-11-14', 1);

-- Layers. raster_path is relative to DATA_DIR and follows the prepared-data contract (Database Design RedGrid).
INSERT INTO layer (id, region_id, dataset_id, key, display_name, kind, data_state, default_on, raster_path) VALUES
  (1,  1, 1, 'elevation',       'Elevation (HiRISE)',          'RASTER', 'HISTORICAL_OBSERVATION', 0, 'jezero/elevation.tif'),
  (2,  1, 1, 'hillshade',       'Hillshade',                   'RASTER', 'DERIVED',                1, 'jezero/hillshade.tif'),
  (3,  1, 1, 'slope',           'Slope',                       'RASTER', 'DERIVED',                0, 'jezero/slope.tif'),
  (4,  1, 1, 'roughness',       'Roughness',                   'RASTER', 'DERIVED',                0, 'jezero/roughness.tif'),
  (5,  1, 5, 'terrain_class',   'Terrain class',               'RASTER', 'LIMITED_CONFIDENCE',     0, 'jezero/terrain_class.tif'),
  (6,  1, 6, 'thermal_inertia', 'Thermal inertia (THEMIS)',    'RASTER', 'HISTORICAL_OBSERVATION', 0, 'jezero/thermal_inertia.tif'),
  (7,  1, 11,'comm_coverage',   'Communication coverage',      'RASTER', 'DERIVED',                0, 'jezero/comm_coverage.tif'),
  (8,  1, 2, 'imagery_hirise',  'HiRISE image',                'RASTER', 'HISTORICAL_OBSERVATION', 0, 'jezero/imagery_hirise.tif'),
  (9,  1, 4, 'imagery_ctx',     'CTX image',                   'RASTER', 'HISTORICAL_OBSERVATION', 0, 'jezero/imagery_ctx.tif'),
  (10, 1, 3, 'elevation_ctx',   'Elevation (CTX, display only)','RASTER','HISTORICAL_OBSERVATION', 0, 'jezero/elevation_ctx.tif'),
  (11, 1, 1, 'hazards',         'Hazards',                     'VECTOR', 'DERIVED',                1, NULL),
  (12, 1, 1, 'rim_scarps',      'Crater rims and scarps',      'VECTOR', 'DERIVED',                0, NULL),
  (13, 1, 10,'science_targets', 'Science targets',             'VECTOR', 'DERIVED',                1, NULL),
  (14, 1, 11,'safe_points',     'Safe points',                 'VECTOR', 'DEMONSTRATION_DATA',     1, NULL),
  (15, 1, 11,'comm_assets',     'Communication assets',        'VECTOR', 'DEMONSTRATION_DATA',     0, NULL),
  (16, 1, 7, 'rover_path',      'Perseverance traverse',       'VECTOR', 'HISTORICAL_OBSERVATION', 1, NULL),
  (17, 1, 5, 'geology_units',   'Geology units (SIM 3464)',    'VECTOR', 'LIMITED_CONFIDENCE',     0, NULL),
  (18, 1, 5, 'landing_ellipse', 'Mars 2020 landing ellipse',   'VECTOR', 'HISTORICAL_OBSERVATION', 0, NULL);

-- Demonstration points (positions from the 3D scene: base at the landing site, comms tower 26 m west, 10 m north, 18 m mast)
INSERT INTO feature (layer_id, feature_type, name, code, geometry_json, science_value, provides_refill, height_m) VALUES
  (14, 'SAFE_POINT',          'Ares Base One (concept habitat)', 'BASE', '{"type":"Point","coordinates":[77.45088573,18.44462715]}', NULL, 1, NULL),
  (15, 'COMMUNICATION_ASSET', 'Comms tower',                     'COMM1','{"type":"Point","coordinates":[77.45042334,18.44479586]}', NULL, 0, 18);

-- SIM 3464 unit -> terrain class (accepted 14 Nov 2026)
INSERT INTO terrain_class_mapping (unit_symbol, unit_name, terrain_class, dataset_id, reason) VALUES
  ('Aeb',   'Eolian bedform unit',        'SAND',          5, 'Wind-blown ripples and dunes'),
  ('su',    'Smooth unit, undivided',     'REGOLITH',      5, 'Smooth, mantled surface'),
  ('ci',    'Crater interior unit',       'REGOLITH',      5, 'Infilled crater floors'),
  ('Njf',   'Jezero floor unit',          'BEDROCK',       5, 'Rock floor with thin cover'),
  ('NHjf1', 'Jezero fan 1 unit',          'BEDROCK',       5, 'Layered delta rock'),
  ('NHjf2', 'Jezero fan 2 unit',          'BEDROCK',       5, 'Layered delta rock'),
  ('Hnpf',  'Nili Planum fan unit',       'BEDROCK',       5, 'Fan deposits'),
  ('Nue',   'Upper etched unit',          'BEDROCK',       5, 'Eroded, exposed rock'),
  ('Nle',   'Lower etched unit',          'BEDROCK',       5, 'Eroded, exposed rock'),
  ('Nnp1',  'Nili Planum 1 unit',         'BEDROCK',       5, 'Plains rock unit'),
  ('Nnp2',  'Nili Planum 2 unit',         'BEDROCK',       5, 'Plains rock unit'),
  ('Nrb',   'Rugged bright unit',         'BEDROCK',       5, 'Rugged rock exposures'),
  ('cr',    'Crater rim unit',            'BOULDER_FIELD', 5, 'Blocky rim material'),
  ('CR',    'Crater riim unit',           'BOULDER_FIELD', 5, 'Jezero''s own rim; name spelled as published'),
  ('ce',    'Crater ejecta unit',         'BOULDER_FIELD', 5, 'Blocky ejecta');

-- Route profiles. MISSION_PRIORITY takes its distance weight from the priority resolver.
INSERT INTO route_profile (key, display_name, distance_weight) VALUES
  ('SAFEST',           'Safest',           0.0),
  ('SHORTEST',         'Shortest',         1.0),
  ('SCIENCE_FOCUSED',  'Science-focused',  0.0),
  ('MISSION_PRIORITY', 'Mission priority', NULL);

-- Route-type limits: team POLICY values carried over from V5 (team proposal, to confirm). Not derived from data.
INSERT INTO profile_rule (route_type, category_group, scale, max_factor, max_vs_hazard) VALUES
  ('SAFEST',           'HAZARD',        2.0, 50, NULL),
  ('SAFEST',           'TERRAIN',       1.5, 20, NULL),
  ('SAFEST',           'SCIENCE',       0.5,  2, 0.5),
  ('SAFEST',           'COMMUNICATION', 1.5, 10, NULL),
  ('SAFEST',           'UNCERTAINTY',   1.5, 50, NULL),
  ('SHORTEST',         'HAZARD',        0.5, 50, NULL),
  ('SHORTEST',         'TERRAIN',       0.3, 20, NULL),
  ('SHORTEST',         'SCIENCE',       0.0,  1, 1.0),
  ('SHORTEST',         'COMMUNICATION', 0.0,  1, NULL),
  ('SHORTEST',         'UNCERTAINTY',   1.0, 50, NULL),
  ('SCIENCE_FOCUSED',  'HAZARD',        1.0, 50, NULL),
  ('SCIENCE_FOCUSED',  'TERRAIN',       1.0, 20, NULL),
  ('SCIENCE_FOCUSED',  'SCIENCE',       2.0, 10, 1.0),
  ('SCIENCE_FOCUSED',  'COMMUNICATION', 1.0, 10, NULL),
  ('SCIENCE_FOCUSED',  'UNCERTAINTY',   1.0, 50, NULL),
  ('MISSION_PRIORITY', 'HAZARD',        NULL, 50, NULL),
  ('MISSION_PRIORITY', 'TERRAIN',       NULL, 20, NULL),
  ('MISSION_PRIORITY', 'SCIENCE',       NULL, 10, 1.0),
  ('MISSION_PRIORITY', 'COMMUNICATION', NULL, 10, NULL),
  ('MISSION_PRIORITY', 'UNCERTAINTY',   NULL, 50, NULL),
  -- rover path is its own group so the rover-path slider scales only near_rover_path
  ('SAFEST',           'ROVER_PATH',    1.0,  2, NULL),
  ('SHORTEST',         'ROVER_PATH',    0.0,  1, NULL),
  ('SCIENCE_FOCUSED',  'ROVER_PATH',    1.0,  2, NULL),
  ('MISSION_PRIORITY', 'ROVER_PATH',    NULL, 2, NULL);

-- Priority presets (team values, prototype). Each row sums to 1.
-- PLACEHOLDER values: to be replaced by weights derived with the Analytic Hierarchy Process (AHP) from the team's
-- pairwise comparisons (principal eigenvector, consistency ratio below 0.10). See RedGrid System Specification.
INSERT INTO priority_preset (key, display_name, description, safety_weight, science_weight, distance_weight,
                             walking_difficulty_weight, return_weight, environment_weight, rover_path_weight, basis) VALUES
  ('BALANCED',        'Balanced',        'Every factor counts; none dominates',          0.25, 0.20, 0.15, 0.15, 0.15, 0.05, 0.05, 'PLACEHOLDER (AHP pending)'),
  ('SAFETY_FOCUSED',  'Safety first',    'Stay far from hazards and rough ground',       0.45, 0.20, 0.10, 0.10, 0.10, 0.03, 0.02, 'PLACEHOLDER (AHP pending)'),
  ('SCIENCE_FOCUSED', 'Science first',   'Pass as many science targets as is safe',      0.20, 0.45, 0.05, 0.10, 0.10, 0.05, 0.05, 'PLACEHOLDER (AHP pending)'),
  ('SHORTEST',        'Shortest',        'Least distance within the hard limits',        0.15, 0.05, 0.50, 0.10, 0.10, 0.05, 0.05, 'PLACEHOLDER (AHP pending)');

-- Categories. Thresholds are planning constants (named in the rule), so they are the same everywhere.
INSERT INTO category (key, display_name, category_group, scope, layer_key, rule, is_reference, bit) VALUES
  ('slope_0_5',        'Slope 0-5 deg',             'TERRAIN',       'SHARED',     'slope',           '0 <= slope < 5 deg',                                        1, 0),
  ('slope_5_10',       'Slope 5-10 deg',            'TERRAIN',       'SHARED',     'slope',           '5 <= slope < 10 deg',                                       0, 1),
  ('slope_10_15',      'Slope 10-15 deg',           'TERRAIN',       'SHARED',     'slope',           '10 <= slope < 15 deg',                                      0, 2),
  ('slope_15_20',      'Slope 15-20 deg',           'TERRAIN',       'SHARED',     'slope',           '15 <= slope <= max_slope_deg (steeper is blocked)',         0, 3),
  ('rough_low',        'Smooth ground',             'TERRAIN',       'SHARED',     'roughness',       'roughness < rough_smooth_max_m',                            1, 4),
  ('rough_medium',     'Medium roughness',          'TERRAIN',       'SHARED',     'roughness',       'rough_smooth_max_m <= roughness < rough_high_min_m',        0, 5),
  ('rough_high',       'Rough ground',              'TERRAIN',       'SHARED',     'roughness',       'roughness >= rough_high_min_m',                             0, 6),
  ('terrain_regolith', 'Regolith / soil',           'TERRAIN',       'SHARED',     'terrain_class',   'terrain class = REGOLITH',                                  1, 7),
  ('terrain_bedrock',  'Bedrock',                   'TERRAIN',       'SHARED',     'terrain_class',   'terrain class = BEDROCK',                                   0, 8),
  ('terrain_sand',     'Sand / ripples',            'TERRAIN',       'SHARED',     'terrain_class',   'terrain class = SAND',                                      0, 9),
  ('terrain_boulder',  'Boulder field',             'TERRAIN',       'SHARED',     'terrain_class',   'terrain class = BOULDER_FIELD',                             0, 10),
  ('near_rover_path',  'On known rover path',       'ROVER_PATH',    'FIXED',      'rover_path',      'distance to traverse < rover_path_buffer_m',                0, 11),
  ('near_rim_scarp',   'Near crater rim or scarp',  'HAZARD',        'SHARED',     'rim_scarps',      'distance to rim or scarp line < rim_buffer_m',              0, 12),
  ('hazard_0_50',      'Hazard within 50 m',        'HAZARD',        'SHARED',     'hazards',         'outside hazard polygon, distance < hazard_near_m (inside is blocked)', 0, 13),
  ('hazard_50_200',    'Hazard 50-200 m',           'HAZARD',        'SHARED',     'hazards',         'hazard_near_m <= distance < hazard_far_m',                  0, 14),
  ('near_science',     'Near science target',       'SCIENCE',       'HUMAN_ONLY', 'science_targets', 'distance to a science target < science_buffer_m',           0, 15),
  ('no_comm',          'No communication coverage', 'COMMUNICATION', 'FIXED',      'comm_coverage',   'no line of sight to any communication asset',              0, 16),
  ('data_missing',     'Data missing',              'UNCERTAINTY',   'FIXED',      '*',               'slope, roughness, terrain_class or hazards has no value (cannot occur inside the routable area; kept for training and wider coverage)', 0, 17);

-- Version 0: hand-set weights, always available
INSERT INTO cost_model (id, version, method, status, trained_on, training_summary, test_score, created_at)
VALUES (1, 0, 'HAND_SET', 'ACTIVE', NULL, 'Hand-set: slope and terrain class = 1 (physics in the base cost); other weights are placeholders until a learned version', NULL, '2026-11-14T00:00:00Z');

INSERT INTO category_weight (model_id, category_key, coefficient, weight, probability, std_error, basis) VALUES
  -- slope and terrain class: energy and time are in the base cost (Minetti, Tobler, terrain factors) -> 1
  (1,'slope_0_5',NULL,1.0,NULL,NULL,'REFERENCE'),        (1,'slope_5_10',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'),
  (1,'slope_10_15',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'), (1,'slope_15_20',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'),
  (1,'terrain_regolith',NULL,1.0,NULL,NULL,'REFERENCE'),  (1,'terrain_bedrock',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'),
  (1,'terrain_sand',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'), (1,'terrain_boulder',NULL,1.0,NULL,NULL,'PHYSICS_IN_BASE'),
  -- no published physics: hand-set placeholders (V5 values) until the learned model replaces them
  (1,'rough_low',NULL,1.0,NULL,NULL,'REFERENCE'),
  (1,'rough_medium',NULL,1.3,NULL,NULL,'PLACEHOLDER'),     (1,'rough_high',NULL,2.0,NULL,NULL,'PLACEHOLDER'),
  (1,'near_rim_scarp',NULL,2.0,NULL,NULL,'PLACEHOLDER'),   (1,'hazard_0_50',NULL,4.0,NULL,NULL,'PLACEHOLDER'),
  (1,'hazard_50_200',NULL,1.5,NULL,NULL,'PLACEHOLDER'),    (1,'near_science',NULL,0.6,NULL,NULL,'PLACEHOLDER'),
  (1,'near_rover_path',NULL,0.9,NULL,NULL,'PLACEHOLDER'),  (1,'no_comm',NULL,1.5,NULL,NULL,'PLACEHOLDER'),
  (1,'data_missing',NULL,5.0,NULL,NULL,'PLACEHOLDER');

INSERT INTO planning_constant (key, value, unit, description, source, data_state) VALUES
  -- Grid and hard limits
  ('grid_cell_m',              8,      'm',     'Size of one routing grid square',                               'Team decision: matches the 3D walking grid; HiRISE DTM resampled from 1 m', 'DERIVED'),
  ('max_slope_deg',            20,     'deg',   'Squares steeper than this are blocked',                         'Prototype assumption; justification in RedGrid System Specification, section How routes are chosen', 'DEMONSTRATION_DATA'),
  ('walk_speed_flat_kmh',      3.0,    'km/h',  'Suited walking speed on flat ground (Tobler curve scaled)',     'Prototype assumption', 'DEMONSTRATION_DATA'),
  -- Category thresholds (one value for the whole site)
  ('rough_smooth_max_m',       0.25,   'm',     'Below this roughness a square is smooth (1 x DTM vertical precision)', 'Placeholder until the DTM precision is read from the product documentation', 'DEMONSTRATION_DATA'),
  ('rough_high_min_m',         0.50,   'm',     'At or above this roughness a square is rough (2 x DTM vertical precision)', 'Placeholder until the DTM precision is read from the product documentation', 'DEMONSTRATION_DATA'),
  ('ti_sand_max',              200,    'J m-2 K-1 s-1/2', 'Regolith with thermal inertia below this becomes sand',  'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('ti_bedrock_min',           600,    'J m-2 K-1 s-1/2', 'Regolith with thermal inertia above this becomes bedrock', 'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('hazard_near_m',            50,     'm',     'Outer edge of the hazard_0_50 band',                            'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('hazard_far_m',             200,    'm',     'Outer edge of the hazard_50_200 band',                          'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('rim_buffer_m',             30,     'm',     'Distance to a rim or scarp line counted as near',               'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('science_buffer_m',         100,    'm',     'Distance to a science target counted as near',                  'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('rover_path_buffer_m',      10,     'm',     'Distance to the rover traverse counted as on the path',         'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('comm_receiver_height_m',   2,      'm',     'Height of the suit antenna above ground for line of sight',     'Prototype assumption', 'DEMONSTRATION_DATA'),
  -- Data-preparation rules (applied by the data tool; stored so the report can name them)
  ('hazard_roughness_m',       1.0,    'm',     'Roughness at or above this marks hazard ground (hazard polygons)', 'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('hazard_min_area_m2',       192,    'm2',    'Smallest hazard polygon kept (3 grid squares)',                 'Team decision', 'DERIVED'),
  ('scarp_slope_deg',          25,     'deg',   'Slope at or above this marks a rim or scarp edge',              'Prototype assumption', 'DEMONSTRATION_DATA'),
  ('scarp_min_length_m',       50,     'm',     'Shortest rim or scarp line kept',                               'Team decision', 'DERIVED'),
  -- Science values
  ('science_value_core_site',  1.0,    '',      'Science value of a rock-core sample site',                      'Team rule: sites NASA chose for sampling', 'DERIVED'),
  ('science_value_other_site', 0.5,    '',      'Science value of other sample-related sites (regolith, atmosphere, witness tubes, depot)', 'Team rule', 'DERIVED'),
  -- Corridor and run limits
  ('corridor_margin_fraction', 0.5,    '',      'Corridor margin as a share of the start-destination distance',  'Team decision', 'DERIVED'),
  ('corridor_min_margin_m',    1000,   'm',     'Smallest corridor margin',                                      'Team decision', 'DERIVED'),
  ('corridor_max_expansions',  2,      '',      'Times the corridor is widened when a route touches its edge',   'Team decision', 'DERIVED'),
  ('max_corridor_cells',       4000000, 'squares', 'Largest corridor calculated (about 12 s on a laptop). A first corridor above it is refused (ROUTE_TOO_LONG); widening stops at it', 'Team policy (prototype), from measured run times', 'DEMONSTRATION_DATA'),
  ('provider_timeout_s',       30,     's',     'Time a remote provider has to answer before the next provider is used', 'Team decision', 'DERIVED'),
  -- Route assessment (RedGrid backend)
  ('risk_margin_high_fraction',     0.10, '', 'Route risk is HIGH when the smaller remaining share of usable oxygen or battery is below this', 'Team policy (prototype)', 'DEMONSTRATION_DATA'),
  ('risk_margin_moderate_fraction', 0.25, '', 'Route risk is at least MODERATE, and limitingResource is named, when the smaller remaining share is below this', 'Team policy (prototype)', 'DEMONSTRATION_DATA'),
  ('geology_offset_m',              200,  'm', 'Largest stated offset of the SIM 3464 map; squares closer than this to a terrain-class boundary count as uncertain in dataConfidence', 'SIM 3464 metadata (Sun and Stack, 2020): random offsets of about 100-200 m', 'HISTORICAL_OBSERVATION'),
  -- Oxygen, battery and work rate
  ('metabolic_rate_w',         300,    'W',     'Work rate used for walking: Apollo 14 EVA average on the Moon (1/6 g), assumed for Mars; no gravity correction',                               'Apollo 14 PLSS report: about 265-310 W measured', 'HISTORICAL_OBSERVATION'),
  -- Terrain energy factors relative to regolith (Pandolf 1977 / Soule and Goldman 1972 terrain coefficients:
  -- blacktop 1.0, dirt road 1.1, loose sand 2.1; divided by dirt road because the Apollo work rate was measured on regolith)
  ('terrain_factor_regolith',  1.00,   '',      'Walking energy on regolith relative to regolith',               'Reference surface (Apollo work rate measured on regolith)', 'MODELLED_CONDITION'),
  ('terrain_factor_bedrock',   0.91,   '',      'Walking energy on bedrock relative to regolith',                'Pandolf / Soule-Goldman: blacktop 1.0 / dirt road 1.1 (Earth, unsuited)', 'MODELLED_CONDITION'),
  ('terrain_factor_sand',      1.91,   '',      'Walking energy on loose sand relative to regolith',             'Pandolf / Soule-Goldman: loose sand 2.1 / dirt road 1.1 (Earth, unsuited)', 'MODELLED_CONDITION'),
  ('terrain_factor_boulder',   1.91,   '',      'Walking energy in a boulder field relative to regolith',        'PLACEHOLDER: no published coefficient; set to the highest known factor (sand) so it is never treated as easy', 'DEMONSTRATION_DATA'),
  ('oxygen_energy_j_per_l',    20100,  'J/L',   'Energy released per litre of oxygen used',                      'Standard indirect calorimetry value', 'MODELLED_CONDITION'),
  ('oxygen_density_g_per_l',   1.429,  'g/L',   'Density of oxygen',                                             'Physical constant', 'MODELLED_CONDITION'),
  ('default_oxygen_kg',        0.6,    'kg',    'Default usable oxygen per crew member',                         'Placeholder - replace with a sourced value', 'DEMONSTRATION_DATA'),
  ('default_battery_wh',       800,    'Wh',    'Default usable suit battery',                                   'Placeholder - replace with a sourced value', 'DEMONSTRATION_DATA'),
  ('default_suit_power_w',     90,     'W',     'Default suit power draw',                                       'Placeholder - replace with a sourced value', 'DEMONSTRATION_DATA'),
  ('default_reserve_fraction', 0.2,    '',      'Share of oxygen and battery that must never be used',           'Prototype assumption', 'DEMONSTRATION_DATA');
