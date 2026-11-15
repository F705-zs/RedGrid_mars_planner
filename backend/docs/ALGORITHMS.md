# RedGrid Backend: algorithms and their scientific basis

Every mathematical or physical choice in the backend, where it comes from, and how sure we are.
References were written from memory and must be checked against the originals before submission. Each is
marked **Verify**. Nothing below is an official NASA EVA limit.

Status labels: **Published**, a formula from the literature. **Method**, a standard technique. **Policy**, a
team decision that cannot be derived. **Placeholder**, to be replaced by a sourced value.

## 1. Coordinates and grid

| Choice | Basis | Status |
|---|---|---|
| Mars 2000 sphere, R = 3 396 190 m | IAU/IAG Mars 2000 reference used by USGS and the Mars 2020 TRN products | Published |
| Equirectangular, standard parallel 0°, central meridian 0° | Same system as the Mars 2020 TRN HiRISE and CTX products, so no resampling of the source data | Method |
| **Anisotropic ground spacing** | With standard parallel 0, east–west scale is cos(latitude) (Snyder 1987, *Map Projections: A Working Manual*, USGS PP 1395). At Jezero (18.44°N) an 8 m cell is 8 m N–S × 7.59 m E–W. Slopes, distances, energy and path lengths all use these true ground spacings | Published (Verify) |
| 8 m routing cell | Team decision: matches the 3D walking grid; large enough to be well above the HiRISE DTM's effective resolution | Policy |
| Local tangent-plane metres for feature distances | Error under 0.1% within 30 km | Method |

**Note for the data tool:** slope must be computed with the same ground spacings (dx = 8·cos(lat), dy = 8 m).

## 2. Walking physics (base cost, oxygen, battery)

| Quantity | Formula | Source | Status |
|---|---|---|---|
| Energy vs gradient | C(i) = 280.5i⁵ − 58.7i⁴ − 76.8i³ + 51.9i² + 19.6i + 2.5 J kg⁻¹ m⁻¹, \|i\| ≤ 0.45 | Minetti et al. 2002, *J. Appl. Physiol.* 93:1039–1046 | Published (Verify), Earth, unsuited |
| Speed vs gradient | v/v_flat = exp(−3.5(\|i + 0.05\| − 0.05)) | Tobler 1993, NCGIA Technical Report 93-1 | Published (Verify) |
| Terrain energy factors | bedrock 0.91, regolith 1.00, sand 1.91 (relative to dirt road 1.1) | Soule & Goldman 1972, *J. Appl. Physiol.* 32:706–708; Pandolf et al. 1977, *J. Appl. Physiol.* 43:577–581 | Published (Verify), Earth |
| Boulder-field factor 1.91 | Highest known coefficient, so it is never treated as easy | Placeholder |
| Work rate 300 W | Apollo 14 PLSS report: EVA average on the Moon (1/6 g). Not corrected for Mars gravity | Historical measurement used as an assumption |
| Flat speed 3 km/h | Prototype value, separate from the 300 W source | Placeholder |
| Oxygen per energy | 20.1 kJ per litre O₂ (indirect calorimetry; Weir 1949, *J. Physiol.* 109:1–9, about 20–21 kJ/L depending on fuel mix); 1.429 g/L at STP | Published (Verify) |
| Battery | suit power × time | Method |

**Absolute level.** E per metre on flat regolith = 300 W ÷ (3 km/h). The published curves only supply the
*relative* change with slope and surface. Check: 0.0256 kg O₂ per km on flat ground is 0.077 kg/h, inside the
draft's 0.07–0.09 kg/h range (tested in `tests/test_physics.py`).

**Direction.** The routing grid has no walking direction, so it uses the mean of uphill and downhill:
(C(i) + C(−i))/2, and the same for 1/v. The chosen path is then re-walked in its real direction for every
number shown to the user. A round trip on the grid equals the real round trip exactly (tested); one way
differs by about ±3–4% on rough terrain (open item P9).

**Not modelled (open item S3).** Mars gravity: the 300 W rate was measured at 1/6 g and the curves at 1 g. Look
at reduced-gravity walking energetics (for example Farley & McMahon 1992, *J. Appl. Physiol.*; Verify).

## 3. Cost of a square

```
base   = d × 1  +  (1 − d) × R / R_flat_regolith               (simple additive weighting)
R      = oxygen per metre / usable oxygen  +  battery per metre / usable battery
cost   = base × exp( Σ_g  clamp(s_g × L_g, −ln M_g, +ln M_g) )  (weighted product model with caps)
```

| Choice | Basis | Status |
|---|---|---|
| Resource share R | The crew is limited by oxygen and battery, so a square's physical cost is the share of each budget it uses. Equal importance of running out of either | Method |
| Normalisation to 1 on flat regolith | Makes distance and resource terms commensurable, so d is a pure weight | Method |
| Simple additive weighting for the base | Standard multi-criteria method for commensurable, normalised criteria (Triantaphyllou 2000, *Multi-Criteria Decision Making Methods: A Comparative Study*; Verify) | Method |
| Weighted product model for preferences | Dimension-free; a neutral factor (1) stays neutral for any importance; equivalent to a weighted sum in log space, which is how step-selection weights are estimated (Triantaphyllou 2000; Verify) | Method |
| Exponent s_g = 7 × slider weight | Normalisation: with seven sliders summing to 1, equal priorities give s = 1 and leave the weights unchanged | Mathematical identity |
| d = w_distance / (w_distance + w_return) | The two base-cost objectives, renormalised between themselves | Method |
| Caps M_g, science limit, route-type scales | Team safety policy carried over from V5 | Policy |
| Science limit | E_science ≥ −v × min(s_hazard × hazardFloor, ln M_hazard): a science pull never exceeds v × the weakest hazard push the route type can produce; window-independent | Policy, precise definition |
| Uncertainty | exponent ≥ 1 and E ≥ 0: missing data is never made cheaper | Policy |
| Overflow | Each E_g ≤ ln M_g, so the largest multiplier is 50·20·10·10·50·2 = 10⁷ | Method (tested) |

**Slope and terrain category weights are 1** in version 0, because the physics already contains them.
A second weight would count slope twice.

**For the model team.** Include log(base cost) as an offset in the step-selection model (integrated
step-selection analysis; Avgar et al. 2016, *Methods Ecol. Evol.*; Verify). statsmodels `ConditionalLogit`
accepts `offset` (checked with 0.15). In simulation, a true preference of +0.50 came out as −0.17 without the
offset and +0.53 with it.

## 4. Hard limits

| Limit | Value | Status |
|---|---|---|
| Max slope | 20° (planning constant). Reasons in RedGrid System Specification. Needs a NASA human-system or analog-EVA source (S4) | Placeholder (prototype assumption) |
| Hazard core | Square centre inside a hazard polygon | Policy |
| Routable area | Only where every routing layer has a value | Policy (missing data never treated as safe) |
| User HAZARD_WARNING | HIGH = blocked circle; MEDIUM = hazard_0_50 band; LOW = hazard_50_200 band, inside the radius | Policy (RedGrid backend) |

## 5. Physical return limit

For each resource separately: Dijkstra from the start, and multi-source Dijkstra from every refill point at
once (the start too when it is a base). A square is blocked when cost(start → square) + cost(square → nearest
refill) exceeds the usable amount (capacity × (1 − reserve)) for oxygen **or** battery. This is the Apollo
"walkback" idea computed exactly on the grid. It replaces the V5 return-budget fraction. If the destination is
beyond the limit, the route is still drawn (calculated without the limit) and marked not feasible.

## 6. Least-cost path

Dijkstra's algorithm (Dijkstra 1959, *Numerische Mathematik* 1:269–271) via scikit-image `MCP_Geometric`
(van der Walt et al. 2014, *PeerJ*).

- **Moves:** 8 neighbours, with true diagonal length √(dx² + dy²).
- **Cost of a move:** the mean of the two squares' costs × length.
- **Science stops:** become ordered waypoints, sorted along the start–destination line, visited leg by leg.
- **Corridor:** margin = max(1 km, 0.5 × trip distance). The corridor is widened (margin × 2, up to twice) when
  a path touches an open edge, or when no path exists inside it.

**Grid property:** an 8-neighbour grid measures distance in octile steps. A raw grid path can be up to about 8%
longer than the straight ground line, and several paths can have the same length. Smoothing (below) removes most of
this. Reported distances are the true length of the smoothed route that is drawn.

**Smoothing (cost-aware string pulling).** Grid paths are staircases. After Dijkstra, each route is straightened
greedily: from each corner, the farthest later point that can be reached in a straight line is found (exponential
then binary search). A shortcut is accepted only if both of these hold:
- No point of it falls in a blocked square. Samples are taken every 1/4 square; a sample exactly on an edge or
  corner checks every square touching it, so a shortcut never squeezes between two blocked squares.
- Its cost is no higher than that of the grid path it replaces. The cost uses the midpoint rule on 1/4-square
  intervals, so one grid step costs exactly what Dijkstra charged.

Other rules:
- Science stops are always kept as corners.
- The walk back to the refill point is smoothed the same way, on the oxygen cost.
- All route numbers are recomputed on the straight segments: points every half square, elevation interpolated
  bilinearly.

On the demo terrain this cut route points from about 500 to 5–10 corners and distance, time and oxygen by 3–4%.
Smoothing is greedy, so two different grid paths can straighten to slightly different lengths. It never changes
which route is chosen or makes it less safe.

**Corridor cap.** The planning constant max_corridor_cells (4 million squares, about 12 s) is checked before any
heavy calculation:
- If the first corridor is larger, the API answers 400 ROUTE_TOO_LONG.
- Widening stops at the cap, and the routes carry a warning.

Measured on synthetic terrain:
- 1 million squares: about 3 s.
- A 10 km diagonal with one science stop: 4.5 s in total.

## 7. Categories (CategoryExtractor, shared with training)

**Thresholds.** All thresholds are planning constants, the same everywhere:
- slope bands 5/10/15/20°
- roughness at 1× and 2× the DTM precision (placeholder 0.25/0.50 m)
- hazard bands 50/200 m
- rim 30 m, science 100 m, rover path 10 m

**Distances.** Distances are exact Euclidean distance transforms on the anisotropic grid (scipy
`distance_transform_edt`, Maurer et al. 2003; Verify). Features up to the largest buffer outside the window are
included by padding. No comm data counts as no coverage, never assumed covered.

## 8. Route numbers

| Field | Definition |
|---|---|
| distanceM | Ground length of the drawn path |
| durationMin | Walking time (Tobler, real direction) + science-stop durations |
| oxygenUsedKg, batteryUsedWh | Real-direction walking + stops at the work rate and suit power |
| oxygenLeftKg, batteryLeftWh | Capacity − (route + walk back to the nearest refill point, real direction) |
| feasible | A path exists, a refill point can be reached, and both resources stay at or above the reserve |
| limitingResource | Resource with the smaller remaining share of usable; NONE when both shares are at least risk_margin_moderate_fraction (0.25) |
| maximumReturnDistanceM | Remaining usable after the route ÷ use per metre on flat regolith, for the limiting resource |
| terrainDifficulty | Length-weighted mean energy multiplier relative to flat regolith (1.0 = flat regolith) |
| scienceScore | Share (0–1) of the science value in the corridor within science_buffer_m of the path |
| hazardCount | Distinct hazards and HIGH/MEDIUM warnings within hazard_near_m of the path |
| missionMatch | 100 × (mission-priority cost of the mission-priority route) ÷ (mission-priority cost of this route). The mission-priority route scores 100; a route with no path scores 0 |
| dataConfidence | Share of path length farther than geology_offset_m (200 m, the stated SIM 3464 offset) from a terrain-class boundary |
| overallRisk | CRITICAL if not feasible. HIGH if the remaining share < 0.10, the path enters the 50 m hazard band, it passes a hazard, or max slope ≥ 15°. MODERATE if the remaining share < 0.25, it enters the 200 m band, max slope ≥ 10°, or any part has no comm. LOW otherwise (thresholds = planning constants and category band edges; Policy) |
| dustStatus | Mean dust optical depth τ over the demo window: < 1 background, 1–2 elevated, ≥ 2 storm conditions. Typical non-storm τ at Mars landing sites stays below about 1 (Lemmon et al. 2015, *Icarus* 251; Verify). Prototype labels; no value → "Data unavailable" |

## 9. Synthetic demonstration data (development only)

`flask make-demo-data` writes contract-conformant files, all labelled DEMONSTRATION_DATA:
- fractal relief
- a delta-front-like scarp up to about 70 m high, cut by ramps
- nine small craters with depth/radius 0.2–0.25 (depth/diameter 0.10–0.125, moderately degraded; fresh simple
  craters ≈ 0.2, Pike 1977; Verify)
- roughness, terrain classes, hazards and rims derived by the contract's rules

Real positions are used for the landing site, the comms tower (18 m mast) and the Perseverance traverse and
Three Forks depot (MMGIS, via the 3D repo).

**Comms coverage** is line of sight from the mast top to a 2 m suit antenna. It includes Mars curvature: drop =
d²/2R, about 15 m at 10 km. Radio refraction in the thin atmosphere is neglected.

**No weather is invented.** Without MEDA files the weather shows "data unavailable".
