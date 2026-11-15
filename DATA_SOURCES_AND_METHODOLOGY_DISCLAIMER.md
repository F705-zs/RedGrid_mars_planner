# RedGrid — Data Sources and Methodology Disclaimer

**Date:** Nov 15, 2026  
**Project:** RedGrid – Integrated Martian Mission-Planning Map & 3D EVA Simulator  
**Event:** NASA Space Apps Challenge 2026  
**Target Study Area:** Jezero Crater, Mars ($77.20^\circ\text{E} - 77.70^\circ\text{E}, 18.20^\circ\text{N} - 18.70^\circ\text{N}$)  

---

## 1. Purpose and Compliance Statement

This document constitutes the official **Data Sources, Methodology, and References Disclosure** for the **RedGrid** project, submitted to the **NASA Space Apps Challenge 2026**. 

In strict adherence to the *Participant Project Submission Guidelines*:
1. **Global Award Eligibility:** RedGrid integrates and directly utilizes multiple **official NASA challenge resources**, demonstrating concrete technological application of NASA mission data to extraterrestrial EVA mission planning.
2. **Comprehensive Attribution:** Every NASA dataset, space agency partner product, external scientific publication, open-source library, and historical baseline is cataloged with its source, provider, DOI/URL, resolution, and exact technical role.
3. **Engineering Disclaimers:** Clear boundaries are defined regarding prototype assumptions, spatial resolution limits, environmental observation scopes, and life-support modeling constraints.

---

## 2. Official NASA Challenge Resources Used

The core functionality of RedGrid relies upon verified, peer-reviewed planetary datasets released by NASA missions and the USGS Astrogeology Science Center:

| Dataset / Product Name | Provider / Mission | Access Link / Identifier | Resolution & Coverage | Role in RedGrid |
|---|---|---|---|---|
| **HiRISE Terrain Relative Navigation (TRN) DTM** | USGS Astrogeology / NASA Mars 2020 | [DOI 10.5066/P9REJ9JN](https://doi.org/10.5066/P9REJ9JN) · [USGS TRN DTM](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40) · [Direct S3 GeoTIFF](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif) | 1.0 m / px native, co-registered onto the 8.0 m routing grid (`4,744,570` routable squares) · Central Jezero delta & landing ellipse | **Primary Elevation & Slope Model:** Generates elevation (`elevation.tif`), hillshade (`hillshade.tif`), slopes (`slope.tif`, bands 0–5°, 5–10°, 10–15°, 15–20°, >20° blocked), surface roughness (`roughness.tif`), hazard polygons (`hazards.geojson`), crater rim scarps (`rim_scarps.geojson`), and base walking time/energy cost. |
| **HiRISE TRN Controlled Orthomosaic** | USGS Astrogeology / NASA Mars 2020 | [USGS Orthomosaic](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first) · [Direct S3 GeoTIFF](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif) | 0.25 m / px native, resampled to 1.0 m / px | **Primary Base Imagery:** Provides ultra-high-resolution photographic context, visible surface feature validation, and 2D/3D map texturing. |
| **CTX Science Investigation DEM Mosaic** | NASA JPL / USGS Astrogeology | [USGS CTX DEM](https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif) | 20.0 m / px · Full Jezero Crater region | **Secondary Regional Topography (`elevation_ctx.tif`):** Seamless regional elevation model covering peripheral areas outside the HiRISE strip for full-crater visual inspection and wider-coverage context. |
| **CTX Controlled Orthomosaic** | NASA JPL / USGS Astrogeology | [USGS CTX Ortho](https://astropedia.astrogeology.usgs.gov/download/Mars/Mars2020/ancillary/M20_JezeroCrater_CTXortho_mosaic_5m.tif) | 5.0 m / px · Full Jezero Crater region | **Secondary Imagery Baseline (`imagery_ctx.tif`):** Regional surface photographic context across Jezero Crater outside the HiRISE corridor. |
| **Perseverance Rover Traverse & Waypoints (Sample Sites)** | NASA / JPL-Caltech MMGIS | [NASA MMGIS Traverse](https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json) · [NASA MMGIS Waypoints](https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json) | GeoJSON LineString (`rover_path.geojson`, 559 sol segments / 522 clipped Jezero segments, Sols 0–1850+) & GeoJSON Points (`science_targets.geojson`, 18 sample/waypoint targets) | **Ground Truth Rover Path & Science Targets:** Displayed as map layers (`rover_path` and `science_targets`), used to score science proximity (`scienceScore`), and used to train shared Martian mobility cost categories. |
| **Mars Environmental Dynamics Analyzer (MEDA)** | NASA PDS Atmospheres Node / Centro de Astrobiología (CAB) | [PDS MEDA Archive](https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda) | Calibrated time-series CSV tables (Sols 1830–1859, 120 raw files aggregated into 1,432 hourly rows in `observations.csv`) | **Regional Meteorology:** Surface pressure (PS, mean $746.38\text{ Pa}$), ground/air temperature (TIRS/ATS, mean $-56.51^\circ\text{C}$), relative humidity (RHS), wind, and dust optical depth context. |
| **NASA Mars Trek Tile Service & IAU Nomenclature** | NASA Solar System Treks / USGS / IAU | [NASA Mars Trek API](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars) · [Planetary Names](https://planetarynames.wr.usgs.gov) | Web Mercator / Equirectangular global tiles (`232 m/px`) & Gazetteer points | **Cartographic Context:** Macro-level map navigation, 3D orbital globe textures, and official nomenclature for Jezero craters, scarps, and valleys. |

---

## 3. External Scientific, Partner & Historical Datasets and Literature

To model human-specific walking physics, surface geological characteristics, and multi-criteria routing where NASA rover datasets require complementary context, RedGrid incorporates the following public scientific resources and peer-reviewed publications:

| Dataset / Publication | Publishing Body / Authors | Access Link / Citation | Format & Content | Role in RedGrid |
|---|---|---|---|---|
| **Geologic Map of Jezero Crater (SIM 3464)** | U.S. Geological Survey (USGS) · *Sun & Stack (2020)* | [DOI 10.3133/sim3464](https://doi.org/10.3133/sim3464) · [SIM 3464 Database](https://pubs.usgs.gov/sim/3464/sim3464_database.zip) | Esri File Geodatabase (`Nili.gdb`), 294 clipped geologic polygons (`geology_units.geojson`) & `landing_ellipse.geojson` | **Surface Geology Classification:** Vector geological contacts and 15 SIM 3464 units mapped into 4 generic terrain cost classes (`BEDROCK`, `REGOLITH`, `SAND`, `BOULDER_FIELD`) plus `200 m` boundary uncertainty offset (`dataConfidence`). |
| **THEMIS Quantitative Thermal Inertia Mosaic** | Arizona State University / NASA Mars Odyssey · *Fergason et al. (2006)* | [THEMIS Global TI](https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_quantitative_30s060e_100mpp) · [Direct ISIS3 Cube](https://asc-astropedia.s3.us-west-2.amazonaws.com/Mars/Odyssey/THEMIS-Global-Thermal-Inertia-Mosaic/Quantitative-32-Bit/THEMIS_TI_Mosaic_Quant_00N060E_100mpp.cub) | 100 m / px raster (tile 00N060E, converted from `.cub` to `thermal_inertia.tif`) | **Soil Consolidation / Sand Detection:** Differentiates fine loose dust/drift sand ($<200\text{ J m}^{-2}\text{ K}^{-1}\text{ s}^{-1/2}$, high-risk sinkage) from solid indurated bedrock ($>600\text{ J m}^{-2}\text{ K}^{-1}\text{ s}^{-1/2}$). |
| **Apollo 14 Lunar Surface Traverses** | Lunar Reconnaissance Orbiter Camera (LROC) / ASU · *Robinson et al.* | [LROC Data Portal](https://data.lroc.im-ldi.com/lroc/view_rdr/SHAPEFILE_APOLLO_14) · [Direct Shapefile ZIP](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/APOLLO_14/APOLLO_14.ZIP) | Shapefiles & GeoJSON (`apollo_14/traverses.geojson`, `apollo_14_segments.csv`, 819 human walking segments) | **Human Surface Mobility Training:** Real extraterrestrial human walking paths used in the offline conditional logit model to calibrate human step-selection preferences. |
| **Assessment of Metabolic Expenditures in Apollo (NASA TN D-7883)** | NASA Technical Reports Server (NTRS) · *Waligora & Horrigan (1975)* | [NASA TN D-7883](https://ntrs.nasa.gov/citations/19750006325) / ALSJ Archives | NASA Technical Note (Historical Technical Report) | **Bioenergetic Baselines:** Provides empirical human metabolic work rates during lunar walks ($900 - 1050\text{ BTU/h} \approx 265 - 310\text{ W}$, baseline $300\text{ W}$). |
| **Apollo 14 PLSS Operations Report & NASA Life Support BVAD** | NASA Manned Spacecraft Center / Hamilton Standard & NASA TP-2015-218570 | [ALSJ PLSS Report](https://www.nasa.gov/history/alsj/a14/Ap14PLSS_OPS-Report.pdf) · NASA/TP-2015-218570 (BVAD) | NASA Contractor / Operations Report & Baseline Values and Assumptions Document | **Life-Support Sizing:** Portable Life Support System primary oxygen tank capacity ($0.60\text{ kg}$ default usable $\text{O}_2$), nominal EVA consumption rate ($\approx 0.077\text{ kg/h}$), and $20\%$ untouchable operational reserve. |
| **Biomechanics of Gradient & Terrain Walking** | *Minetti et al. (2002)*; *Tobler (1993)*; *Soule & Goldman (1972)*; *Pandolf et al. (1977)*; *Weir (1949)* | *J. Appl. Physiol.* 93:1039–1046; NCGIA TR 93-1; *J. Appl. Physiol.* 32:706–708 & 43:577–581; *J. Physiol.* 109:1–9 | Peer-reviewed biomechanics & indirect calorimetry equations | **Physics of a Square (`physics.py`):** 5th-degree slope energy polynomial $C(i)$, Tobler speed curve $v(i)$, terrain energy multipliers (`0.91` bedrock, `1.00` regolith, `1.91` sand/boulder), and $20.1\text{ kJ/L O}_2$ conversion. |
| **Multi-Criteria & Discrete Choice Routing Literature** | *Triantaphyllou (2000)*; *McFadden (1974)*; *Avgar et al. (2016)*; *Dijkstra (1959)*; *Snyder (1987)* | Springer MCDM Ch. 2; *Frontiers in Econometrics*; *Methods Ecol. Evol.* 7:619–630; *Numer. Math.* 1:269–271; USGS PP 1395 | Mathematical optimization & cartographic projection literature | **Routing & Cost Formulation:** Dimension-free Weighted Product Model (WPM), Conditional Logit / Integrated Step-Selection Analysis (iSSA), 8-neighbor Dijkstra pathfinding, and anisotropic equirectangular ground spacing ($\cos\varphi$). |

---

## 4. Open-Source Software, Libraries, and Tools

RedGrid is constructed using open-source, permissive-license software libraries. All third-party software components are acknowledged below:

- **GDAL / OGR (Geospatial Data Abstraction Library) & Rasterio:** Version 3.x (MIT/X & BSD 3-Clause License). Utilized for `/vsicurl/` remote streaming, raster re-projection, coordinate warping, DEFLATE-compressed tiling, and runtime GeoTIFF window reading.
- **PROJ (Cartographic Projections Library):** Version 9.x (MIT License). Defines Mars 2000 Sphere ellipsoidal coordinate transformations.
- **GeoPandas & Shapely:** (BSD 3-Clause License). Vector polygon clipping, spatial buffering, and GeoJSON serialization.
- **SQLite:** Version 3.38+ (Public Domain). Embedded relational database engine supporting spatial/JSON queries (`json_valid`) and view-based provider chains.
- **Python & Flask:** Python 3 (PSF License) and Flask 3.x (BSD 3-Clause License). Backend REST API server, dependency-injected provider container (`CostProviderI`, `PriorityResolverI`, `ResourceProviderI`), spatial data engineering, and offline statistical training.
- **NumPy, SciPy, scikit-image & ImageCodecs:** (BSD 3-Clause License). High-performance numerical raster array processing, Euclidean distance transforms (`scipy.ndimage.distance_transform_edt`), and 8-neighbor geometric Dijkstra least-cost pathfinding (`skimage.graph.MCP_Geometric`).
- **Pillow (PIL Fork) & Matplotlib:** (HPND / PSF License). Dynamic RGBA terrain texture rendering (`/terrain/texture`) and scientific route visualization.
- **React 19, TypeScript & Vite:** (MIT & Apache-2.0 License). Modern frontend web application framework and bundler.
- **TanStack Start, TanStack Router & TanStack Query:** (MIT License). Type-safe frontend routing and asynchronous API state management.
- **Leaflet.js & React-Leaflet:** (BSD 2-Clause & MIT License). Interactive 2D planetary GIS mapping interface, raster overlay rendering, and vector layer inspection.
- **Three.js:** (MIT License). Interactive 3D Mars orbital descent (`ARES/DESCENT`) and first-person Jezero surface walk with live footstep streaming (`public/mars3d/`).
- **Recharts, Tailwind CSS v4, Radix UI / shadcn-ui & Lucide Icons:** (MIT & ISC License). Multi-metric route comparison radar chart, dark-mode mission control UI components, and iconography.
- **Pytest & Vitest:** (MIT License). Automated testing frameworks executing 120 backend tests and 48 frontend unit and live API contract tests.

---

## 5. Core Scientific & Engineering Disclaimers

### A. Mandatory Prototype Engineering Notice
> **PROTOTYPE NOTICE:**  
> The human-mobility walking speeds, metabolic work rates, oxygen consumption rates, spacesuit battery power draws, and safe-point walkback limits utilized throughout RedGrid are **prototype engineering assumptions**, not certified NASA Extravehicular Activity (EVA) flight rules.  
> RedGrid is developed as an interactive planning tool for the NASA Space Apps Challenge 2026. While all formulas are mathematically grounded in published Apollo lunar mission data and terrestrial biomechanics literature, they have not undergone NASA operational flight certification and **must not be used for real extraterrestrial mission decisions**.

### B. The "NoData / Missing Data" Safety Principle
- **Fail-Safe Integrity:** In critical extraterrestrial exploration, unknown terrain is hazardous. RedGrid strictly adheres to the rule: **Missing data is never assumed to be safe.**
- **Verified Routable Polygon (`routable_area.geojson`):** The 1 m HiRISE DTM and Orthomosaic cover the central Jezero delta and landing corridor (`4,744,570` squares at 8.0 m spacing). Live EVA routing is strictly restricted to the verified `routable_area` polygon where every routing layer (`elevation`, `slope`, `roughness`, `terrain_class`, and `hazards`) has valid, non-missing observations.
- **Regional Context & Uncertainty Category (`data_missing`):** Outside the HiRISE corridor, the 20 m CTX DEM (`elevation_ctx.tif`) and 5 m CTX Orthomosaic (`imagery_ctx.tif`) provide regional visual context on the map. For wider-coverage model training and boundary evaluation, the category `data_missing` (`bit 17`, group `UNCERTAINTY`, weight `5.0`) guarantees that missing data is never rewarded (`exponent >= 1`, `E >= 0`).
- **Visual & Confidence Disclosure:** Every calculated route reports a quantitative `dataConfidence` score (the fraction of path length farther than SIM 3464's `200 m` positional offset from any geologic unit boundary), and layers using fallback/regional data are explicitly labeled `LIMITED_CONFIDENCE` or `DEMONSTRATION_DATA`.

### C. Scope of In-Situ Weather Telemetry (MEDA)
- **Local Point Telemetry vs. Regional Gradient:** Data collected by the MEDA instrument on Perseverance represents localized surface observations at the rover's exact position.
- **30-Sol Operational Window:** Sols 1830–1859 were selected to capture current seasonal Martian atmospheric trends ($L_s$ diurnal temperature swings from $-80^\circ\text{C}$ to $-15^\circ\text{C}$,mean $-56.51^\circ\text{C}$, and $\approx 746.38\text{ Pa}$ atmospheric pressure).
- **Extrapolation Boundary:** Atmospheric temperature and pressure readings establish regional mission operational windows (safe daytime EVA duration vs. extreme nighttime cryogenic hazards); they are not micro-climate forecasts across high-elevation crater rim topography.

### D. Mars Coordinate Systems & Map Projections
- **Internal Datum & Reference Ellipsoid:** All spatial rasters and vector features are standardized to the **Mars 2000 Sphere** defined by the International Astronomical Union (IAU):
  $$\text{Semi-major axis } a = 3,396,190\text{ m}, \quad \text{Semi-minor axis } b = 3,396,190\text{ m}$$
- **Longitude Convention:** East-positive longitude ($0^\circ \text{ to } 360^\circ$ East).
- **Projection & Anisotropic Ground Spacing:** Equirectangular (Equidistant Cylindrical) projection with standard parallel at $0^\circ$ latitude. Because east–west scale varies as $\cos(\text{latitude})$ (Snyder 1987, USGS PP 1395), an $8\text{ m}$ routing cell at Jezero ($18.44^\circ\text{N}$) measures $8.00\text{ m}$ N–S by $7.59\text{ m}$ E–W; all slopes, Euclidean distance transforms, and path lengths in the backend use these exact anisotropic ground spacings.
- **Client-Side Transformation:** Coordinates are transformed into $[lat, lon]$ pairs strictly at the Leaflet client rendering boundary.

### E. Metabolic Oxygen Conversion Methodology
- RedGrid converts mechanical and physiological work into mass of oxygen consumed using bioenergetic relations:
  $$\text{Oxygen Rate } (\text{kg/h}) = \frac{\text{Metabolic Work Rate } (\text{W}) \times 3600\text{ s/h}}{20,100\text{ J/L}} \times 0.001429\text{ kg/L}$$
- For the baseline walking rate of $300\text{ W}$ (Apollo 14 EVA average), this evaluates to $\approx 0.0768\text{ kg }\text{O}_2/\text{hour}$ ($\approx 0.08\text{ kg/h}$ on flat regolith, or $0.0256\text{ kg/km}$ at $3\text{ km/h}$), scaling dynamically with slope (`Minetti 2002`) and surface terrain factor (`Soule & Goldman 1972`). Combined with a default $0.60\text{ kg}$ primary oxygen capacity and $20\%$ untouchable reserve ($0.48\text{ kg}$ usable walk + walkback budget), this is consistent with the NASA Life Support Baseline Values and Assumptions Document (BVAD, NASA/TP-2015-218570), labeled in the database as `HISTORICAL_OBSERVATION` / `MODELLED_CONDITION`.

---

## 6. Intellectual Property, Licensing & Ethics Statement

1. **Public Domain & Open Science:** All primary datasets utilized in RedGrid (NASA Mars 2020, USGS Astrogeology, NASA PDS, and LROC) are published under United States public domain or open scientific access policies.
2. **Attribution & Non-Commercial Use:** All data providers and academic publications have been appropriately credited. The project is created strictly for educational, scientific, and non-commercial competition purposes.
3. **NASA Branding Protection:** In accordance with NASA Space Apps rules, no official NASA insignias, "meatball" logos, "worm" logotypes, mission patches, or federal flags have been copied, altered, or embedded into AI-generated promotional graphics or mockups.
4. **Data Reproducibility:** Every clipped GeoTIFF, GeoJSON traverse, and MEDA time-series table in `backend/data/` and `training_data/` is indexed in `manifest.json` and `categories_and_constants.json`, ensuring complete auditability and reproducibility of the RedGrid pathfinding pipeline.
