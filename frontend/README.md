# RedGrid — Frontend Web Application

Interactive 2D & 3D Martian EVA Mission-Planning Interface for **Jezero Crater, Mars** (`18.38°N, 77.58°E`).

## Key Capabilities

1. **Interactive 2D Map Explorer (`src/components/map/`)**
   - Multi-layer planetary GIS viewer powered by Leaflet (`1.9.4`) and live backend raster textures (`/api/v1/regions/1/terrain/texture`).
   - Toggleable layers for **HiRISE/CTX Imagery**, **Slope**, **Roughness**, **Terrain Classification**, **Thermal Inertia**, **UHF Communication Coverage**, **Perseverance Rover Traverse**, **Safe Havens**, and **Science Targets**.
   - Interactive Point Inspector (`POST /api/v1/regions/1/inspect`) showing exact elevation, slope, roughness, ground category, and MEDA weather context at any clicked coordinate.
2. **EVA Mission Planner & Multi-Route Comparison (`src/components/mission/`)**
   - Configure mission start/destination, EVA objective, astronaut oxygen/battery budgets, and priority profile (`BALANCED`, `SAFETY_FIRST`, `SCIENCE_FOCUSED`, `SHORTEST`, `LOW_EFFORT`, `SAFE_RETURN`, `FOLLOW_ROVER`, or custom weighted mix).
   - Compare all 4 simultaneously computed candidate paths (`SAFEST`, `SHORTEST`, `SCIENCE_FOCUSED`, `MISSION_PRIORITY`) via interactive elevation profiles, radar charts, and life-support consumption metrics.
3. **Immersive 3D Mars Surface Walk (`public/mars3d/`)**
   - Built with Three.js: walk across a 3D terrain mesh of the Octave Tarpeienne / Perseverance landing region (`77.4509°E, 18.4446°N`), plant waypoints (`M`), record astronaut footsteps (`R`), and import them directly into the 2D planner (`POST /api/v1/missions/{id}/footsteps`).

## Running Locally

```bash
npm install
npm run dev
```

Open `http://localhost:8080`. Ensure the RedGrid Flask backend is running on `http://127.0.0.1:5000` (configured via `VITE_API_BASE_URL` in `.env.example`).

## Running Tests

```bash
npm test
```
