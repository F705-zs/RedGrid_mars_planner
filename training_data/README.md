# RedGrid — Prepared Model Training Datasets (`training_data/`)

> **Current Status:**  
> All geospatial extraction, anisotropic distance transforms, and negative step-sampling required to train RedGrid's **Step-Selection Conditional Logistic Regression (`CostModel Version 1`)** have been completed and exported into this directory.  
> In the live application (`backend/instance/redgrid.sqlite3`), **Model Version 0 (`HAND_SET` + Published Physics)** is currently active so the planner runs deterministically out-of-the-box while offline model fitting and held-out validation (`TODO 1` in [`../FUTURE_ROADMAP_AND_TODOS.md`](../FUTURE_ROADMAP_AND_TODOS.md)) are finalized.

---

## Files in This Directory

| File | Rows / Size | Description |
|---|---|---|
| **`jezero_step_choice_dataset.csv`** | `43,855` rows (`5,495` choice strata) | Ready-to-fit conditional logit design matrix. At every `10 m` step along real traverses, compares the **1 chosen step** (`chosen = 1`) against **15 feasible alternative steps** (`chosen = 0`) sampled around the surrounding ring, with all 18 binary terrain/hazard/science category columns and `base_cost` offset. |
| **`training_routes.csv`** | `522` segments | Clipped Mars 2020 *Perseverance* rover drive segments inside the Jezero Crater study box (with 20% marked `is_held_out = 1` for out-of-sample route overlap evaluation). |
| **`apollo_14_segments.csv`** | `819` segments | Real human lunar EVA walking segments from **Apollo 14** (LROC / ASU shapefiles) used to transfer human step-selection behavior. |
| **`meda_observations.csv`** | `1,432` hourly rows | Aggregated NASA Mars 2020 **MEDA** environmental telemetry across Sols `1830–1859` (pressure, air/ground temperature, wind, humidity, dust optical depth). |
| **`categories_and_constants.json`** | `18` categories + `34` constants | Exact bit positions (`0..17`), category rules, and planning constants exported from `redgrid.sqlite3` so offline training scripts use the exact same thresholds as the live routing engine. |
| **`demo_window.json`** | `1` operational window | Metadata for the 30-sol environmental demonstration window (`sol_1830` to `sol_1859`). |

---

## How the Offline Model Fits into the Live Backend

1. **Train Offline:** Fit a conditional logit model (`statsmodels.discrete.conditional_models.ConditionalLogit`) on `jezero_step_choice_dataset.csv` grouped by `stratum_id`, using `np.log(base_cost)` as the offset (Avgar et al. 2016).
2. **Convert Coefficients to Multiplicative Weights:** Compute $w_c = \exp(-\hat{\beta}_c)$ for each category $c \in \{0\dots17\}$.
3. **Validate on Held-Out Segments:** Verify that Dijkstra routes computed with $w_c$ achieve at least $+0.05$ higher 20 m corridor overlap on held-out segments (`is_held_out = 1`) than `Version 0`.
4. **Activate in SQLite or via HTTP Microservice:** Insert a new row in `cost_model` (`version = 1`, `status = 'ACTIVE'`) or serve the model via `POST /v1/cost-factors` (`HttpModelCostProvider`).
