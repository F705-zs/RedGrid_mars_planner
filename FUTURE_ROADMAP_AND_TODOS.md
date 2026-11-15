# RedGrid — Current Model Status & Future Roadmap (`TODOs`)

> **Transparency Note for NASA Space Apps Judges:**  
> RedGrid was engineered with a strict separation between **what runs deterministically today** and **how learned statistical/ML models plug in next**.  
> - **What is LIVE today (`CostModel Version 0 — HAND_SET + Published Physics`):** The routing engine, 8.0 m Jezero Crater multi-layer grid (`4,744,570` squares), physics-based slope/terrain energy model (`Minetti 2002`, `Tobler 1993`, `Soule & Goldman 1972`, `NASA BVAD`), hard safety/walkback barriers, 8-neighbor Dijkstra pathfinder, 2D/3D web app, and **all cleaned training datasets (`5,495` step-choice strata / `43,855` candidate steps in [`training_data/`](training_data/))** are 100% built, populated, and tested (`168/168` tests passing).  
> - **What is on our Future Roadmap (`CostModel Version 1+`):** Training and activating the offline statistical/ML models on the prepared `training_data/` tables and connecting live spacesuit telemetry streams through our pre-built `CostProviderI`, `PriorityResolverI`, and `ResourceProviderI` interfaces.

---

## 1. Current Baseline vs. Target Learned State

| Component | Current Status in Repo (`Active Today`) | Target Future State (`Roadmap TODO`) |
|---|---|---|
| **Base Slope & Surface Energy** | **Live (`physics.py`):** 5th-degree Minetti (2002) slope polynomial + Tobler (1993) speed curve + Soule & Goldman (1972) terrain multipliers (`0.91` bedrock, `1.00` regolith, `1.91` sand) + Weir/BVAD $\text{O}_2$ conversion (`0.077 kg/h` at `300 W`). | **TODO 3:** Add $0.38\,g$ Martian partial-gravity Froude scaling (Farley & McMahon 1992) and explicit xEMU thermal/leakage overhead. |
| **Category Cost Weights (`CostProviderI`)** | **Live (`Version 0 — HAND_SET`):** Active in `redgrid.sqlite3` (`category_weight` table). Slope & terrain class weights are `1.0` (`PHYSICS_IN_BASE`); roughness, hazard buffers, science pull, and comms weights use conservative engineering baseline values. | **TODO 1 & 2:** Fit **Conditional Logit (`Version 1`)** on `training_data/jezero_step_choice_dataset.csv` and deploy **Continuous ML Cost Microservice (`HttpModelCostProvider`)**. |
| **Priority Presets (`PriorityResolverI`)** | **Live (`AlgorithmPriorityResolver`):** Dimension-free Weighted Product Model (Triantaphyllou 2000) with 4 engineering preset profiles (`BALANCED`, `SAFETY_FOCUSED`, `SCIENCE_FOCUSED`, `SHORTEST`) + custom 7-slider user mix. | **TODO 2:** Derive preset weights via formal **Analytic Hierarchy Process (AHP)** pairwise matrices from EVA flight controllers (`CR < 0.10`) or an adaptive **`HttpModelPriorityResolver`**. |
| **Life-Support Budgets (`ResourceProviderI`)** | **Live (`Defaults` + `USER_INPUT`):** Uses NASA BVAD defaults (`0.60 kg` $\text{O}_2$, `800 Wh` battery, `20%` reserve) or user-entered mission overrides (`resource_reading` table). | **TODO 4:** Activate the `SENSOR` data source in `ResourceProviderI` to ingest live spacesuit biometric & PLSS telemetry during an EVA. |

---

## 2. Detailed Engineering `TODO` List

### `TODO 1` — Fit & Promote `CostModel Version 1` (Integrated Step-Selection Conditional Logit)
All data preparation for **Model 1** is complete and stored in [`training_data/`](training_data/):
- **`training_data/jezero_step_choice_dataset.csv`**: `43,855` rows across `5,495` choice strata (`1` real chosen step vs. `15` ring alternatives per stratum at `10 m` spacing).
- **`training_data/apollo_14_segments.csv`**: `819` human lunar EVA walking segments (Apollo 14 EVA-1 & EVA-2).
- **`training_data/training_routes.csv`**: `522` Mars 2020 *Perseverance* traverse segments across Jezero Crater.

**Next Steps to Complete Training:**
1. Fit a **stratified Conditional Logistic Regression** (`statsmodels.discrete.conditional_models.ConditionalLogit`) with `offset = ln(base_cost)` (Integrated Step-Selection Analysis, Avgar et al. 2016) so learned coefficients $\beta_c$ capture residual human/rover terrain preferences without double-counting physical slope energy:
   $$P(y_{s,j}=1 \mid X_s) = \frac{\exp(\text{offset}_{s,j} + \beta^\top x_{s,j})}{\sum_{k=1}^{16}\exp(\text{offset}_{s,k} + \beta^\top x_{s,k})}, \qquad w_c = e^{-\beta_c}$$
2. Run [`backend/redgrid/services/evaluation.py`](backend/redgrid/services/evaluation.py) on the 20% held-out traverse segments (`is_held_out = 1` in `training_route`) and verify the falsification gate:
   $$\text{mean}\left(\text{overlap}_{20\text{m}}(\text{Version 1})\right) - \text{mean}\left(\text{overlap}_{20\text{m}}(\text{Version 0})\right) \ge +0.05$$
3. Insert the validated weights into `cost_model` (`version = 1`, `method = 'CONDITIONAL_LOGIT'`, `status = 'ACTIVE'`)—the routing engine will immediately use them with zero code changes.

---

### `TODO 2` — Train & Plug In the Two Advanced ML Microservices (`HttpModelCostProvider` & `HttpModelPriorityResolver`)
Our backend already includes verified HTTP provider clients ([`backend/redgrid/providers/cost.py`](backend/redgrid/providers/cost.py), [`backend/redgrid/providers/priority.py`](backend/redgrid/providers/priority.py)) and a working reference server ([`backend/tools/mock_model_provider.py`](backend/tools/mock_model_provider.py)):
1. **Model A — Continuous Sub-Meter Hazard & Slip Cost Predictor (`POST /v1/cost-factors`)**:
   - Train a gradient-boosted / CNN terrain model on raw `25 cm` HiRISE orthomosaic patches, `1 m` local slope curvature, and `100 m` THEMIS thermal inertia to predict continuous per-cell traversability multipliers instead of discrete step-function bands.
   - Start the microservice and set `REDGRID_COST_PROVIDER_URL=http://127.0.0.1:8001/v1/cost-factors` in `.env`. At startup, `registry.verify()` validates the contract and automatically falls back to `AlgorithmCostProvider` on timeout.
2. **Model B — Context-Aware Priority Resolver (`POST /v1/priority-scales`)**:
   - Replace static preset weights with an AHP-calibrated and MEDA-weather-aware priority resolver that dynamically boosts `SAFETY` and `RETURN` exponents when dust optical depth $\tau$ rises or remaining daylight decreases.

---

### `TODO 3` — Martian Partial-Gravity ($0.38\,g$) & Spacesuit Biomechanics Calibration
- Currently, `physics.py` uses Earth $1.0\,g$ relative slope/terrain curves (Minetti 2002; Soule & Goldman 1972) anchored to the Apollo 14 $0.16\,g$ lunar EVA mean metabolic rate (`300 W`).
- **Future Work:** Incorporate partial-gravity Froude-number walking energetics (Farley & McMahon 1992) and pressurized planetary suit joint-torque penalties from NASA Johnson Space Center's ARGOS (Active Response Gravity Offload System) trials to model $0.38\,g$ Martian locomotion directly.

---

### `TODO 4` — Live Spacesuit Telemetry & Mobile Rover Refill (`ResourceProviderI`)
- **Live Suit Sensor Stream:** Implement an HTTP/WebSocket `SensorResourceProvider` feeding `resource_reading` rows (`source = 'SENSOR'`) for real-time suit $\text{O}_2$ pressure, $\text{CO}_2$ metox/amine scrubber saturation, cooling-water loop margin, and heart-rate-derived `METABOLIC_RATE_W`.
- **Dynamic Mobile Refill Assets:** Allow a pressurized rover or portable $\text{O}_2$ cache to move along the `rover_path` layer as a time-dependent `provides_refill = 1` safe point, updating the multi-source Dijkstra walkback envelope in real time.

---

### `TODO 5` — Multi-Landing-Site Planetary Expansion
- Because all site-specific thresholds and layers live in SQLite (`region`, `dataset`, `layer`, `planning_constant`), running [`backend/tools/prepare_redgrid_data.py`](backend/tools/prepare_redgrid_data.py) on new NASA PDS / USGS DTMs will allow RedGrid to support:
  - **Northeast Syrtis / Midway** (Mars 2020 extended mission corridor)
  - **Arcadia Planitia & Mawrth Vallis** (candidate human Mars landing sites)
  - **Lunar South Pole (Shackleton / Malapert Massif)** for NASA **Artemis III / IV** lunar surface EVAs.
