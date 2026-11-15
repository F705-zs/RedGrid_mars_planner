# RedGrid — AI Usage Disclaimer

**Date:** Nov 15, 2026  
**Project:** RedGrid – Integrated Martian Mission-Planning Map & 3D EVA Simulator  
**Event:** NASA Space Apps Challenge 2026  

---

## 1. Purpose and Scope
The RedGrid team used generative and agentic AI tools as assistants for technical writing, system design documentation, code drafting, automated geospatial data engineering pipelines, full-stack integration verification, and presentation/deployment preparation. Every architectural decision, data source choice, coordinate standardization, and final result was established, verified, and approved by the human team.

This statement constitutes our official **"Use of SI / AI"** disclosure for the NASA Space Apps Challenge 2026, complying with all Participant Project Submission Guidelines. It covers all project material: the project draft, change plans, cost-weight model specifications, class specifications, database design and SQLite DDL schema, API contracts, architectural Mermaid diagrams, frontend build prompts, the data-source register, automated geospatial data processing pipelines, offline training dataset generation, full-stack testing, presentation visual assets, and application source code.

> **Two kinds of "model" in RedGrid:**  
> The internal cost-weight model in RedGrid is **not** generative AI. It is an empirical statistical model (a conditional logistic regression / step-selection function) designed by the team to learn terrain avoidance and attraction weights offline from historical Apollo astronaut and Mars rover traverses. This disclaimer concerns external AI assistant tools used during project development.

---

## 2. Where AI Was Used
We utilized **Claude (Anthropic)** and **Google Antigravity / Gemini (Google DeepMind)** as our AI assistants. The division of assistance and human oversight across project areas is detailed below:

| Project Area | How AI Helped | What the Team Did |
|---|---|---|
| **Project Draft & Change Plans (V1–V7)** | Structuring sections, drafting and editing prose, maintaining narrative consistency across architectural iterations. | Conceived the core problem statement, defined mission scope, made every design decision; rigorously reviewed and edited all versions. |
| **Cost-Weight Model Description** | Articulating methodological options, drafting the step-selection formulation and validation test protocol. | Chose the mathematical method (conditional logit), defined alternative sampling parameters, selected training datasets, and established the pass criteria. |
| **Class Specification, Database Design, SQL Schema** | Drafting class definitions, relational schemas, SQLite DDL scripts, and cross-checking consistency against domain specifications. | Defined domain requirements, reviewed all tables and constraints, executed and validated the SQLite schema against edge-case queries. |
| **API Contract** | Drafting REST endpoint signatures, request payloads, response schemas, and mock JSON fixtures. | Specified endpoints and system data flow; checked payloads against domain class models. |
| **Diagrams (Class & ER, Mermaid)** | Generating Mermaid.js syntax from class and database specification documents. | Checked that every relationship, cardinality, foreign key, and enumeration strictly matched architectural requirements. |
| **Frontend Build Prompt** | Composing a comprehensive, self-contained implementation brief for the UI workspace. | Defined the UI/UX user journey, screen layouts, mapping interface requirements, and reviewed the final prompt. |
| **Application Code (Backend, Frontend & 3D Scene)** | Assisting with code scaffolding, pluggable provider protocol interfaces (`CostProviderI`, `PriorityResolverI`, `ResourceProviderI`), route serialization logic, React/Leaflet/Three.js components, and unit test drafting. | Integrated, tested, and debugged all backend services, 2D/3D frontend views, and routing pipelines; owns and maintains the codebase. |
| **Dataset Register & Curation** | Compiling data links into structured tabular registers and flagging dead links for manual verification. | Manually opened and verified every NASA and external source; evaluated licensing and suitability for Jezero crater analysis. |
| **Geospatial Data Engineering & Raster Clipping** | Drafting and executing automated GDAL 3 / Rasterio streaming pipelines, configuring VSI curl chunking/retries for remote striped TIFFs, downsampling 25 cm HiRISE ortho to 1 m via average resampling, resampling routing rasters onto the co-registered 8.0 m grid, converting ISIS3 `.cub` thermal inertia to GeoTIFF, and enforcing tiled DEFLATE compression. | Selected the Jezero bounding box (77.20°–77.70°E, 18.20°–18.70°N), validated spatial resolutions, verified elevation ranges (-2665 m to -1640 m), and verified map layer alignment in GIS. |
| **PDS4 Environmental Data Harvesting (MEDA)** | Writing and executing an automated PDS4 directory crawler with SSL handling to discover, batch-download, and organize the 30 most recent sols (120 CSV files, 420.75 MB) of calibrated environmental telemetry (pressure, temperature, humidity, ancillary) and aggregating them into 1,432 hourly summary observations. | Selected the 30-sol window (sol_1830 to sol_1859) to capture current Martian seasonal conditions, filtered derived products over raw telemetry, and verified column schemas against database design. |
| **Data Source Verification, SQLite Seeding & Step-Choice Training Tables** | Auditing coordinate reference frames (Mars 2000 Sphere), checking NoData coverage percentages, generating `manifest.json`, populating the production `redgrid.sqlite3` database, and extracting the 5,495-stratum / 43,855-row step-selection training dataset (`jezero_step_choice_dataset.csv`, `apollo_14_segments.csv`, `training_routes.csv`). | Confirmed the fallback hierarchy (HiRISE to CTX DEM), set the uncertainty penalty rules for missing data, verified all database foreign keys and constraints, and approved the final data-source register. |
| **End-to-End Contract Verification & Automated Testing** | Executing and verifying 120 backend `pytest` tests (API endpoints, cost math, walking physics, anisotropic grid geometry, provider chains) and 48 frontend `Vitest` unit and live API contract tests (`RG_LIVE_API=1`), plus removing legacy scaffolding and cleaning repository structure. | Defined the test scenarios, verified known Perseverance traverse waypoints (Octave Tarpeienne Landing Site to Belva Crater) against calculated routes, and approved all test assertions. |
| **Presentation Visuals, Slide Deck & GitHub Pages Packaging** | Rendering high-resolution matplotlib/Pillow figures directly from the real 8.0 m Jezero DEM and live backend route outputs (`demo_real_jezero_routes.png`, `demo_puzzle_and_formulas.png`), generating the 5-slide judge presentation (`.pptx` and interactive 3D-themed HTML deck), and configuring the `/docs` GitHub Pages deployment bundle. | Authored the presentation narrative, scientific/mathematical/programmatic hypotheses, design rationale, and future two-model roadmap; reviewed and simplified all slide content for judging. |

*AI-assisted code and data pipelines are also explicitly acknowledged in repository documentation, comments, and README files, adhering to Space Apps submission guidelines.*

---

## 3. What AI Did Not Do
The intellectual core, system architecture, and scientific integrity of RedGrid represent original human engineering, guided by our supervising faculty:

1. **No Generative AI in the Live Application:** RedGrid does not invoke external LLMs or generative AI APIs at runtime. All route pathfinding is executed deterministically using Dijkstra’s algorithm over a multi-criteria cost grid, weighted by the team's trained statistical model.
2. **No Synthesized or AI-Generated Planetary Data:** Topographic rasters, controlled imagery, surface geology, and environmental readings originate strictly from published NASA, USGS, and PDS archives. No AI tool synthesized, modified, interpolated, or fabricated any planetary data values.
3. **No Hallucinated Mission Parameters:** Human walking speeds, metabolic work rates ($300\text{ W}$), and oxygen consumption conversions ($0.077\text{ kg/h}$, rounded to $0.08\text{ kg/h}$ on flat ground, with $0.60\text{ kg}$ default usable tank capacity and $20\%$ reserve) derive from historical Apollo mission records, the NASA Life Support Baseline Values and Assumptions Document (BVAD, NASA/TP-2015-218570), and published biomechanics literature. They are explicitly designated as *prototype engineering assumptions*, never certified NASA EVA flight rules.
4. **Human Autonomy over Design & Strategy:** The problem statement, route profiles, algorithmic fallback rules, safety-first constraints, and feature prioritization were conceived, evaluated, and finalized solely by the human team.

---

## 4. Verification and Quality Assurance
To guard against AI inaccuracies, hallucinations, or misattributions, all machine-generated content underwent systematic human review:

- **Source Verification:** Every dataset link was opened, evaluated, and confirmed by a team member before inclusion in the formal register.
- **Code & Schema Execution:** SQL schemas, GDAL/Rasterio data pipelines, and routing algorithms were executed, profiled, and verified on real data across 168 automated tests (120 backend `pytest` + 48 frontend `Vitest`); no code was accepted without hands-on verification.
- **Architectural Cross-Auditing:** Documentation, API contracts, class specifications, and ER diagrams were cross-checked for bidirectional consistency.
- **Branding & Intellectual Property Protection:** No NASA logos, flags, official seals, or mission patches were generated, altered, or incorporated into AI-generated visual media.
- **Privacy & Security:** No personal, private, or confidential data was exposed to external AI APIs during development.

---

## 5. Team Declaration
We, the RedGrid team, declare that this disclosure is complete, transparent, and accurate. Generative and agentic AI tools served strictly as force-multiplying technical assistants. The team takes full responsibility for the methodology, software implementation, data analysis, and conclusions presented in this submission.

- [x] Claude (Anthropic) and Google Antigravity / Gemini disclosed with specific technical ownership in Section 2.
- [x] Zero AI-generated synthetic data or unverified NASA metrics utilized in the solution.
- [x] All external libraries and datasets attributed in the Data Sources and Methodology Disclaimer.
