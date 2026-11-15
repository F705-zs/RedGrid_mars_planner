# RedGrid Backend

Flask + SQLite backend for RedGrid, built from the RedGrid documents: Project draft, Class Specification, Database
Design and API Contract. The weight model is excluded; its place is the **CostProvider** contract, and the
always-available local algorithm uses the version 0 weights from the database.

## Quick start (Windows, macOS or Linux, Python 3.10+)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

flask --app redgrid init-db            # create instance/redgrid.sqlite3 (schema + RedGrid seed)
flask --app redgrid make-demo-data     # SYNTHETIC terrain so the frontend can connect today (labelled DEMONSTRATION_DATA)
flask --app redgrid run                # http://localhost:5000/api
```

Check it is running: `curl http://localhost:5000/api/health`. Run the tests: `pytest -q` (120 tests, about 1 minute; every endpoint is called with valid and invalid data).

**For the demo, use the production server** (`flask run` is for development only):

```bash
waitress-serve --listen=127.0.0.1:5000 --threads=4 --call redgrid:create_app
```

**Try the API without the frontend:** import `docs/RedGrid_API.postman_collection.json` into Postman
(File > Import). It has all 49 requests with example bodies; run "Create mission" first, which saves the mission id
for the others.

Requirements:
- **SQLite 3.38+.** The app refuses to start otherwise. Check with `python -c "import sqlite3; print(sqlite3.sqlite_version)"`.
- **Python packages.** `rasterio` ships GDAL inside its wheels, so no separate GDAL install is needed to *run*
  the backend. The data-preparation tool needs GDAL itself.

## Connect the database

The database is one SQLite file, `REDGRID_DATABASE` (default `instance/redgrid.sqlite3`).

| Command | What it does |
|---|---|
| `flask --app redgrid init-db` | Creates it from `redgrid/schema/redgrid_schema.sql` (25 tables, 2 views, all seed data). **Drops** an existing file |
| `flask --app redgrid check-data` | Checks the prepared files against the contract; loads nothing |
| `flask --app redgrid load-data` | Checks, then loads the prepared files (vectors, routable area, demo window, MEDA, manifest) |

To switch from the demo data to real data:

```bash
flask --app redgrid init-db        # restores the real layer labels
# put the data tool's output in $REDGRID_DATA_DIR/jezero/ (see "Prepared data" below)
flask --app redgrid load-data
```

## Connect the frontend

- **Base URL:** `http://localhost:5000/api`. In the RedGrid app, set `VITE_REDGRID_API_URL=http://localhost:5000/api`.
- **CORS:** allowed origins come from `REDGRID_CORS_ORIGINS`. The default is localhost 8080, 5173 and 3000.
- **Every endpoint, shape and error code** follows the RedGrid API Contract.
- **Integration notes:** see `docs/FRONTEND_INTEGRATION.md`.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| REDGRID_DATABASE | instance/redgrid.sqlite3 | SQLite file |
| REDGRID_DATA_DIR | data | Folder holding `jezero/` (prepared data) |
| REDGRID_CORS_ORIGINS | localhost:8080, 5173, 3000 | Frontend origins |
| REDGRID_COST_PROVIDERS | algorithm | Chain order, e.g. `model,algorithm`. The last one must be local |
| REDGRID_PRIORITY_RESOLVERS | algorithm | e.g. `model,algorithm` |
| REDGRID_RESOURCE_PROVIDERS | sensor,defaults | The sensor is not ready until a URL is set |
| REDGRID_MODEL_COST_URL, REDGRID_MODEL_PRIORITY_URL, REDGRID_SENSOR_URL | (empty) | Remote providers (RedGrid API Contract, Appendix A) |

## Plugging in the model (for the model team)

1. Build a service that follows RedGrid API Contract, Appendix A. `tools/mock_model_provider.py` is a working template:
   `python -m tools.mock_model_provider --port 5055`.
2. Set `REDGRID_COST_PROVIDERS=model,algorithm` and `REDGRID_MODEL_COST_URL=http://localhost:5055`.
3. Every route then names the provider that answered. If the model is down, slow (over 30 s) or answers wrongly,
   the algorithm answers instead and the route carries a warning.

Weights trained offline (Cost-Weight Model V1) need no service: `CostModelRepository.save()` and `activate()`
publish a new version, and the algorithm provider uses it at once.

## Prepared data (what the data tool must produce)

The full contract is in Database Design RedGrid. In short, `DATA_DIR/jezero/`:

**Routing rasters.** All on one 8 m grid in Mars 2000 equirectangular (eqc, lat_ts 0, lon_0 0, R 3396190), as
tiled DEFLATE GeoTIFFs:

| File | Content | No data |
|---|---|---|
| elevation.tif | metres | −9999 |
| slope.tif | degrees, Horn method | −9999 |
| roughness.tif | metres | −9999 |
| terrain_class.tif | 1 regolith, 2 bedrock, 3 sand, 4 boulder field | 255 |
| comm_coverage.tif | 1 covered, 0 not covered | 255 |
| hillshade.tif | display shading | 255 |

Slope must use the **ground** spacing: dx = 8·cos(lat) m, dy = 8 m (see `docs/ALGORITHMS.md` §1).

**Vectors.** `vectors/*.geojson` in lon/lat: hazards, rim_scarps, science_targets (with scienceValue),
safe_points, comm_assets, rover_path, geology_units, landing_ellipse, routable_area.

**Tables.** `demo_window.json`, `meda/observations.csv` (sol, observed_at, variable, unit, value, source), and
optionally `../manifest.json` from the download script.

The rasters may cover the region box or a sub-box: outside the file means no data.

## Swapping a piece (the puzzle)

Every repository and provider has a formal interface (`redgrid/interfaces.py`). To replace one, point its slot to
your class in the app config. For example, `create_app({"REPOSITORY_OVERRIDES": {"routes": "mypkg.PostgresRouteRepository"}})`,
or `PROVIDER_OVERRIDES` with keys like `"cost.model"`. Slots are listed in `redgrid/registry.py`. **Every piece is
checked when the app starts.** A class with a missing or misnamed method, an unknown slot, or a chain whose last
provider is not local stops the app at launch with a message naming the problem.

## Layout

```
redgrid/
  __init__.py      app factory, CORS, error handlers, commit-on-success
  config.py        settings (REDGRID_* environment variables)
  db.py            SQLite connection and init (requires 3.38+)
  schema/          redgrid_schema.sql (single source of truth)
  enums.py, models.py, geo.py, physics.py
  repositories/    the only code that reads the database or the prepared files
  providers/       contracts, ProviderChain, local algorithm + HTTP model/sensor providers, array codec
  services/        catalog, location, mission, route (routing.py maths, evaluation.py numbers), report,
                   category_extractor (shared with the training package)
  controllers/     the five controllers (Flask blueprints under /api)
  loader.py        prepared-data checks and loading;  demo_data.py  synthetic demonstration data
  cli.py           init-db, check-data, load-data, make-demo-data
tools/mock_model_provider.py   reference remote provider (Appendix A)
tests/                         physics, cost maths, providers (including a live HTTP model), full API
docs/ALGORITHMS.md             every mathematical and physical choice with its source
docs/FRONTEND_INTEGRATION.md   what the frontend needs to change
```

## Differences from the RedGrid documents (decided while building; the RedGrid SQL is updated)

| Change | Why |
|---|---|
| route.id and mission.id are AUTOINCREMENT | The contract says route ids change on recalculation; SQLite otherwise reuses deleted ids |
| Three planning constants added (37 in total): risk_margin_high_fraction 0.10, risk_margin_moderate_fraction 0.25, geology_offset_m 200 | Thresholds behind overallRisk, limitingResource and dataConfidence, so they carry a source like every other threshold |
| Ground spacing (anisotropic cells) | Correctness: east–west metres in the data system are cos(lat) shorter on the ground |
| HAZARD_WARNING annotations feed the categories (HIGH blocks, MEDIUM and LOW set the 50 m and 200 m bands) | The documents did not say how warnings affect routing |
| Science stops are waypoints, visited in order along the start–destination line; their duration adds time, oxygen and battery | Same |
| The window includes the refill point nearest the destination | So the walk back can be traced |
| No path inside the corridor → widen first; still none → straight start–destination line, feasible false, missionMatch 0, explicit warning | Same |
| Duplicate also copies annotations | Convenience; resources are copied as the contract says |
| Corridor size cap: planning constant max_corridor_cells (4 million squares, about 12 s); a first corridor above it gives 400 ROUTE_TOO_LONG; widening stops at it with a warning | Keeps the API responsive on the larger real HiRISE area |
| Routes are smoothed: corners are straightened only where the shortcut crosses no blocked square and costs no more; science stops stay; all numbers recalculated on the straight segments | Removes grid zig-zags; distances were up to ~8% too long |
| Formal interfaces checked at start-up; pieces swappable by configuration | Safe replacement of parts |
