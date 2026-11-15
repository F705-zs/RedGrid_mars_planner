# Connecting the RedGrid Frontend to the Backend API

The backend serves exactly the RedGrid API Contract. When connecting a frontend client, replace any mock data with
early data model. These are the changes needed, roughly in order.

## 1. Point the app at the API

`.env`: `VITE_REDGRID_API_URL=http://localhost:5000/api`. `src/lib/api/client.ts` already switches from mock data
to live calls when this is set.

## 2. Replace the domain types

Use the RedGrid API types (RedGrid API Contract, "Object shapes"). The 13 Nov partial export already had `src/types.ts` for V4;
extend it with the API contract fields:
- Region.routableArea
- Mission.objective and priorityMix
- Route.costProvider, priorityResolver, window, calculatedAt
- LocationInfo.routable, roughnessM, terrainClass and terrainClassDataState
- Report.caveats, providersUsed, terrainClassMapping and demoWindow
- CategoryWeight.basis and PriorityPreset.basis

Remove the old Site, crewSize, durationSols and landingSiteId model.

## 3. Mission form (setup screen)

- Start and destination: picked on the map (or typed lon/lat). Grey out everything outside `region.routableArea`;
  the API answers 400 `OUT_OF_COVERAGE` (details.field = "start" | "dest") for points outside it.
- Objective (optional, up to 500 characters).
- Priority: preset buttons from GET /priority-presets, plus **Custom**. Custom shows the presets with a percent
  each; the total must be 100. Compute weights = Σ(percent/100 × preset weights) live and show the seven sliders;
  the user can fine-tune. Send both `priorityMix` and `priorities`.
- Oxygen, battery, work rate, suit power, reserve and "start is a base", prefilled from GET /planning-constants
  (`default_oxygen_kg`, `default_battery_wh`, `metabolic_rate_w`, `default_suit_power_w`,
  `default_reserve_fraction`), labelled "Default – not measured" until edited.

## 4. Route comparison

- POST /missions/{id}/routes takes a few seconds (about 2–5 s on the demo data). Show a loading state and send
  one request at a time.
- Show `costProvider.name` + `version` on each route and `warnings` (a fallback from the model to the algorithm
  is reported there).
- A route with `feasible: false` and the warning "No route found…" is only the straight start–destination link:
  draw it dashed.

## 5. Map layers

- **Vector layers:** GET /regions/1/layers/{key}/geojson.
- **Raster overlays** (slope, roughness, terrain_class, comm_coverage, hillshade): GET
  /regions/1/terrain/texture?west&south&east&north&size&layer=… as a Leaflet image overlay on the same bbox.
  Transparent pixels mean no data: draw them grey, never smoothed.
- **3D:** GET /regions/1/terrain for the elevation grid.

## 6. Weather

GET /demo-window and the `environment` of LocationInfo. In the demo data there is no MEDA, so the weather says
"data unavailable" on purpose.

## 7. Errors

Every error is `{"error": {"code", "message", "details"}}`. Show `message`; branch on `code`:

| Code | What to do |
|---|---|
| OUT_OF_REGION | Highlight the point |
| OUT_OF_COVERAGE | Highlight the point |
| MISSION_FINALIZED | Switch to read-only |
| ROUTES_NOT_CALCULATED | Offer "Calculate routes" |
| DATA_NOT_PREPARED | Show "terrain data not loaded" |
