# F1 2026 Predictions - Release Notes

## [v6.1.0] - 2026-08-23
### Race Weekend Auto-Gate & FastF1 Calendar Integration

#### 🏎️ Race Weekend Auto-Gate
- **`is_race_window_active()`**: Dynamically queries the FastF1 Ergast API schedule for 2026 and future seasons. Restricts Databricks Lakehouse workflow runs strictly to active **Race Weekends (Friday through Sunday)** and **Post-Race Mondays**.
- **Non-Race Skipping**: Automatically skips execution on non-race days (e.g. Wednesdays of gap weeks) without wasting compute resources or sending spurious notification emails.
- **`--force` CLI Flag**: Added `--force` flag to `databricks_entrypoint.py` and DABs task parameters so manual pipeline triggers and integration test runs can bypass the gate on demand.

#### ⚙️ DABs Workflow Schedule Alignment (`f1_2026_race_predictions_job`)
- Renamed workflow from `f1_2026_daily_predictions_job` to **`f1_2026_race_predictions_job`** (`[${bundle.target}] F1 2026 Race Weekend Predictions Workflow`).
- Updated Quartz cron schedule to **`0 0 6 ? * FRI-MON`** (runs Friday through Monday at 06:00 UTC).

#### 🔒 Trigger.dev CI Version Pinning
- **`.github/workflows/docker.yml`**: Pinned `pnpm dlx trigger.dev@4.4.6 deploy --env prod` to match `package.json` `@trigger.dev/*` package dependencies (`4.4.6`), resolving the CI version mismatch error (`ERR_PNPM_BAD_PM_VERSION`).

#### 📧 Gmail & Notification Transport Hardening
- Resolved dataclass contract alignment between `RaceVerdict`, `RaceBriefingPayload`, and `GmailSMTPChannel`. Live HTML briefings now render and deliver directly to `restrepojuanjo@gmail.com`.

---

## [v6.0.0] - 2026-08-23
### Databricks Lakehouse & Unity Catalog MLOps Integration (Phase 15 Complete)

#### ⚡ Databricks Asset Bundles (DABs) & Lakeflow Jobs
- **`databricks.yml`**: Configured root bundle specification for multi-environment deployment (`dev`, `staging`, `prod`) targeting Unity Catalog schemas (`f1_2026_dev.race_pace`, `f1_2026_prod.race_pace`).
- **`resources/jobs.yml`**: Engineered 3-task Lakeflow workflow (`f1_2026_daily_predictions_job`):
  1. `run_medallion_pipeline`: Runs DLT Bronze → Silver → Gold feature extraction.
  2. `train_and_register_champion`: Executes model training & promotes `@champion` alias in Unity Catalog.
  3. `dispatch_notifications`: Dispatches automated Gmail + Discord race briefing cards.
- **Serverless Compute Optimization**: Configured jobs for Databricks Serverless compute (`client: "2"` REPL channel) with explicit Pydantic v2 (`pydantic>=2.7.0`, `pydantic-settings>=2.3.0`) and NumPy (`numpy>=1.26.0,<2.0`) environment resolution.

#### 🌊 Delta Live Tables (DLT) Medallion Architecture
- **`src/f1_predictions/databricks/pipelines/f1_medallion_pipeline.py`**:
  - **Bronze Layer (`telemetry_bronze`)**: Raw telemetry ingestion using in-memory DataFrame transformation.
  - **Silver Layer (`laps_silver`)**: Automated lap cleaning and validation with DLT expectations (`expect_or_drop` for invalid lap times, `expect_or_fail` for missing driver IDs).
  - **Gold Layer (`driver_features_gold`)**: Feature aggregation per driver (mean pace, stddev, tire degradation slope) optimized for sub-second feature lookups.
- **`resources/pipelines.yml`**: Serverless DLT pipeline definition with `spark.databricks.delta.allowArbitraryProperties.enabled=true` for custom Delta table metadata.

#### 🎯 MLflow 3 & Unity Catalog Model Registry
- **`src/f1_predictions/databricks/mlflow_utils.py`**: Real MLflow experiment tracking (`/Shared/f1_2026/race_pace`) and model promotion using Unity Catalog aliases (`@champion` and `@challenger`), superseding legacy stage transitions.
- **`databricks_entrypoint.py`**: Dedicated Databricks job entrypoint handling `--run-mode {train,notify}` and `--season`, ensuring clean separation from local CLI utilities (`main.py`).

---

## [v5.1.0] - 2026-06-05
### Dynamic Calendar Integration & Vercel 404 Fix (Phase 14 Partial)

#### 🗓️ Automated Calendar Sync
- **`src/scripts/sync_calendar.py`** (new): Fetches the official 2026 F1 event schedule directly from the FastF1 API and writes `reports/2026/calendar.json` as the single source of truth. Eliminates all manual date hardcoding.
- Identified and corrected a critical calendar error: Round 5 is the **Canadian Grand Prix** (May 24), not Emilia Romagna (which is not on the 2026 calendar).
- All 22 rounds correctly mapped with official FIA names, dates, and filesystem slugs.

#### 🛠️ Dashboard Calendar Reader
- **`dashboard/src/utils/fileReader.ts`**: `getFullCalendar()` now reads `reports/<year>/calendar.json` dynamically. Removed the 38-line manually-guessed dictionary. Includes graceful fallback with a `console.warn` if the JSON is missing.

#### 🔒 Vercel 404 Fix
- **`dashboard/src/components/RaceSelector.tsx`**: Upgraded to accept a `fullCalendar` prop. Rounds without built pages (upcoming races) are now rendered as `disabled` `<option>` elements — clicking them is blocked at the HTML level, preventing 404 errors on Vercel.
- **`dashboard/src/pages/race/[round].tsx`**: Passes `fullCalendar` via `getStaticProps` to `RaceSelector`.
- **`dashboard/src/pages/index.tsx`**: "Next Race" card and calendar grid now compute the upcoming round dynamically from real dates instead of hardcoding Round 6.

#### ⚙️ Infrastructure
- `.gitignore`: Added `!reports/**/calendar.json` exception so the build artifact is tracked in git (all other JSON in `reports/` remains ignored).

---

## [v5.0.0] - 2026-06-05
### Cloud Scalability & Durable Worker (Phase 12 Complete)
- **Cloud Caching Ingestion**: Implemented a Supabase S3 cloud caching layer (`f1-cache`) using Boto3 to persist race artifacts and FastF1 cached files, enabling zero-dependency serverless worker execution.
- **Dockerized Worker Deployment**: Configured Github Actions (`.github/workflows/docker.yml`) to automatically build and deploy the Trigger.dev worker container on master push.
- **Visual Crossing Integration**: Integrated real-time hourly and 7-day proactive weather forecasts to enrich Friday predictions.

### Human-in-the-Loop & Live Timing (Phase 13 Complete)
- **Trigger.dev Waitpoint Approvals**: Reconfigured Monday brief distributions to wait for manual human approval (`src/trigger/approval_types.ts` & `src/trigger/f1_tasks.ts`).
- **Antigravity Agentic Swarms**: Created specialized collaborative agents (Aero, Strategy, Weather) orchestrated by a Coordinator agent to generate multi-perspective markdown insights.
- **Live Timing Telemetry Adapters**: Built real-time SignalR socket streaming client `live_timing.py` and alerts monitor `scripts/live_monitor.py` for tracking live pace deltas.

### Quality Gates & Strict Type Hardening
- **Strict Testing Strategy**: Added unit tests for Antigravity swarms and live socket listeners, hitting an **81.44%** code coverage threshold.
- **Pytest Asyncio Configuration**: Integrated `pytest-asyncio` into the Python package environment and `pyproject.toml` tool overrides.

---

## [v4.4.4] - 2026-06-03
### Data Science & Pipeline Resilience
- **Monaco Circuit Metadata Engine**: Integrated an advanced F1 circuit metadata configuration (`config.yaml`) defining circuit characteristics including `overtake_difficulty`, `tyre_wear_type`, and `safety_car_probability`.
- **Intelligent ML Features**: Added `circuit_overtake_difficulty` to the Gold-layer feature matrix, amplifying the importance of qualifying performance at street circuits like Monaco.
- **Dynamic Context Injection**: Configured Gemini to analyze predictive outputs conditionally based on circuit types (e.g. emphasizing pit loss time for street circuits).
- **Automated Fallbacks**: Hardened pipeline lap generation to automatically detect circuit total laps instead of defaulting to 50.

---

## v4.4.4 - DevOps & Data Science Alignment
**Date**: May 2026

### 🛡️ Code Quality & Security Hardening
- **Strict Pre-Commit Enforcement**: Integrated `pre-commit` hooks orchestrating `ruff`, `mypy`, and `pytest` locally to ensure 100% type safety and zero linting errors prior to commit.
- **NPM Supply-Chain Fixes**: Implemented strict package overrides in `package.json` to resolve 12 deep transitive vulnerabilities stemming from the Trigger.dev SDK.
- **CI Synchronization**: Ensured GitHub Actions workflow perfectly matches local validation standards by executing `mypy` locally via the `uv` environment, exposing all typing stubs (`fastapi`, `pydantic`).

---

## v4.4.3 - Autonomous UI & End-to-End Formatting
**Date**: May 2026

### 🎨 Visual & Telemetry Perfection
- **End-to-End Fastest Lap**: Completely automated the extraction of the actual Fastest Lap via `fastf1` in the python backend (`master_pipeline.py`) and dynamically bound both predicted and actual Fastest Laps to the frontend UI, eliminating all hardcoded placeholders.
- **KaTeX Math Rendering**: Integrated `remark-math` and `rehype-katex` into the AI Race Analysis React markdown engine, perfectly rendering complex LaTeX SHAP formulas (e.g., `$\Delta t$`) with official KaTeX styling.
- **Predictions Deduplication**: Refactored `fileReader.ts` to intelligently aggregate per-lap ML predictions, resolving duplicate driver rows in the Finishing Order table by precisely averaging multi-lap forecasts into a single robust performance delta.

---

## v4.4.2 - Gemini Model Migration & AI Pipeline Cleanup
**Date**: May 2026

### 🤖 AI Narrative Reliability
- **Gemini Migration**: Updated the AI narrative path to use `gemini-3.1-pro-preview` as the primary model after Google shut down `gemini-3-pro-preview`.
- **Fallback Resilience**: Added `gemini-3.5-flash` as the automated fallback so race reports can still publish when Pro preview quota, billing, or availability blocks a run.
- **Workflow Cleanup**: Consolidated AI reporting through `master_pipeline.py`, removed the stale AI summarizer workflow that referenced a missing script, and aligned GitHub Actions secret names around `F1_GEMINI_API_KEY`.

---

## v4.4.1 - Dashboard Synchronization & Test Coverage
**Date**: May 2026

### 🖥️ Full-Stack Alignment
This patch release ensures the UI completely supports the newly integrated StackingRegressor.
- **Frontend Sync**: Updated `dashboard/src/utils/fileReader.ts` and `PredictionsTable.tsx` to read and prioritize the `predicted_laptime_stack_s` metrics, with a seamless fallback to XGBoost for legacy reports.
- **Test Integrity**: Added explicit pytest coverage for `StackingPaceRegressor` in the models suite.

---

## v4.4.0 - Advanced Model Ensembling (Stacking)
**Date**: May 2026

### 🧠 Predictive Engine Upgrade
This release tackles Phase 12 of the Roadmap, significantly upgrading the predictive intelligence of the platform by moving from isolated models to an advanced meta-learning architecture.

- **StackingRegressor Integration**: Combined our top-performing base learners (XGBoost and LightGBM) using a `StackingPaceRegressor`.
- **Bayesian Ridge Meta-Model**: Implemented a Bayesian Ridge regressor at the meta-level to intelligently blend predictions, explicitly targeting a Mean Absolute Error (MAE) reduction below 0.150s.
- **Cross-Validated Stacking**: Engineered internal 5-fold cross-validation during the stacking process to completely eliminate data leakage between base-learner training and meta-learner blending.
- **Pipeline-Wide Refactoring**: 
  - `predict_season.py`, `simulate_race.py`, and `generate_reports.py` now all execute the StackingRegressor as the primary source of truth for driver standings and performance forecasts.
- **Robust Environment Configuration**: Improved `SettingsConfigDict` (`extra="ignore"`) to handle autonomous Trigger.dev environment variables gracefully during local pipeline testing.

---

## v4.3.0 - Durable Orchestration & Agentic Autopilot
**Date**: May 2026

### 🤖 Autonomous MLOps with Trigger.dev
This release completes the transition to a fully autonomous, industrial-grade execution model by integrating Trigger.dev v3.

- **Durable Orchestration**: Migrated the manual/scheduled pipeline to Trigger.dev, ensuring 100% reliability for long-running (1h+) race simulations and background tasks.
- **Hybrid Node/Python Worker**: Implemented a sophisticated worker architecture that leverages TypeScript for orchestration and a production-grade Python environment for data science.
- **Scheduled Autonomous Loop**: 
  - **Friday Forecasts**: Automatic pre-race ML simulations triggered by race weekend metadata.
  - **Monday Audits**: Automatic post-race telemetry analysis and SHAP-powered narrative generation.
- **Future-Proof Robustness**:
  - **Driver Inheritance**: Implemented dynamic grid discovery that inherits the previous race's drivers if official entry lists are unavailable for future rounds.
  - **Synthetic Projections**: Added fallback logic for "Pre-Race" forecasts that generates theoretical strategy and lap data when real telemetry hasn't occurred yet.
  - **Extended TTL**: Increased task maximum duration to 20 minutes to accommodate heavy data ingestion from the FastF1 API.
- **Full Quality Certification**: Maintained 100% passing test suites and >80% coverage across the new orchestration layer.

---

## v4.2.0 - High-Fidelity UI & Readability Overhaul
**Date**: May 2026

### 🎨 Visual Excellence & Accessibility
This release focuses on industrial-grade UI/UX standards, ensuring the dashboard is as readable as it is beautiful across all device scales.

- **Global Readability Bump**: Systematic increase of base font sizes to ensure critical race data is legible on both high-resolution monitors and mobile devices.
- **Hierarchical Typography**: Redesigned section headers (`Race Timeline`, `Finishing Order`, `Tyre Intelligence`, `AI Race Analysis`) using a responsive `text-sm md:text-base` scale for better structural clarity.
- **Proportional Subtitles**: Synchronized section subtitles and metric card labels to scale dynamically with headers, maintaining a consistent 2px visual hierarchy.
- **Micro-Readability Fixes**: Eliminated legacy "tiny" font sizes (8px-10px). Tyre stints, search placeholders, and team tags now use a minimum 10px-12px scale for immediate recognition.
- **Refined Data Display**: Increased font weight and size for driver codes and lap times in results tables, matching the professional F1 broadcast feel.
- **Prose Content Optimization**: Enhanced the AI Race Analysis section with `prose-base` scaling and responsive heading sizes for a superior long-form reading experience.

## v4.1.0 - Autonomous Autopilot (Proactive Intelligence)
**Date**: May 2026

### 🚀 The "Full Autopilot" Era
This release completes the autonomous loop by adding pre-race forecasting to the automated schedule.

- **Friday Pre-Race Briefing**: Automated trigger (Friday 18:00 UTC) that runs ML simulations and sends a "Prediction Preview" before the weekend starts.
- **Predictive Detection**: Added `detect_upcoming_race` to the orchestration engine, allowing the system to identify and prepare for future events.
- **Resilient Pipeline**: Re-engineered `master_pipeline.py` to support "Prediction-Only" mode when actual race results are not yet available.
- **Unified Orchestration**: Enhanced `scheduled_sync.yml` to intelligently switch between Friday (Preview) and Monday (Audit) modes.

## v4.0.0 - Autonomous Intelligence & Scheduled Reporting
**Date**: May 2026

### 🤖 The "Proactive" Era
This major release transforms the platform from a reactive tool into a **proactive, event-driven intelligence system**. It introduces automated race detection, scheduled reporting pipelines, and multi-channel notification delivery.

- **Automated Race Detection**: Implemented a "Smart Gate" detector using FastF1 metadata to autonomously trigger pipelines only when a race weekend concludes.
- **Scheduled Synchronization Workflow**: New GitHub Actions pipeline (`scheduled_sync.yml`) runs every Monday/Wednesday at 09:00 UTC to sync data and generate reports.
- **"Monday Verdict" Engine**: Introduced a post-race evaluation module that computes Mean Absolute Error (MAE) and positional accuracy (Winner, Podium, Top-10) against official results.
- **Premium Multi-Channel Notifications**:
  - **Strategy Pattern Dispatcher**: Modular architecture for delivering briefings across multiple platforms.
  - **High-Fidelity HTML Emails**: Dark-mode, F1-branded briefings sent via Gmail SMTP.
  - **Discord Race Cards**: Structured embeds for real-time team alerts.
- **Static Chart Exporter**: Integrated Plotly + Kaleido for server-side generation of high-quality race position charts embedded directly in reports.
- **Enhanced Quality Standards**:
  - **Coverage > 80%**: Maintained strict 80% coverage threshold with comprehensive tests for notification and detection modules.
  - **Mypy Strict Compliance**: Full type safety across the new automation layer.

### 🛠️ Technical Retrospective & Lessons Learned
- **The "Headless" Dependency Trap**: Encountered a build failure where `kaleido` (the static chart engine) required Linux system libraries (`libnss3`, `libatk`, etc.) that were missing in the slim Docker image. Resolved by adding a dedicated graphics-dep layer to the `Dockerfile`.
- **CI Linting Granularity**: Discovered that `ruff check` passes don't guarantee `ruff format --check` passes. Standardized the local development workflow to always run `uv run ruff format` before pushing to avoid CI blocking.
- **Strategy Pattern Payoff**: The decision to use the Strategy Pattern for notifications allowed us to pivot from a simple print statement to a full Gmail/Discord integration in under an hour without touching core business logic.

---


## v3.0.0 - Industrial MLOps Inception
**Date**: May 2026

### 🏭 The "Industrial" Era
This release transforms the project from a research codebase into a **production-grade inference platform**. It focuses on stability, portability, and professional software engineering standards.

- **FastAPI Inference Microservice**: Launched the official REST API (`/predict`, `/health`) with strict Pydantic validation, immutable startup loading (*lifespan*), and sub-10ms inference latency.
- **Multi-Architecture Docker (AMD64/ARM64)**: Implemented a sophisticated parallel CI/CD pipeline that builds native images for both cloud servers (Intel/AMD) and local development (Apple Silicon).
- **Automated Manifest Merging**: Integrated `docker buildx imagetools` to create professional multi-platform manifests under a single `latest` tag.
- **Strict Quality Control (L3 Maturity)**:
  - **Mypy Strict**: Achieving 100% type safety across the core package.
  - **Ruff Linting**: Clean codebase following modern Python standards.
  - **Test Coverage > 80%**: Reached **82.52%** coverage with new unit tests for Reliability and Era Normalization modules.
- **Container Optimization**: Consolidated Docker layers and implemented `--link` support (BuildKit) for faster, more efficient image builds.

---

## v2.2.2 - AI Robustness & Strategic Persona Engineering
**Date**: May 2026

### 🛠️ Strategic & Technical Enhancements
- **High-Fidelity Structured Narratives**: Standardized AI prompt engineering to enforce a professional numbered-list format (Stints, Aero, Driver Deltas) with technical bullet points, ensuring visual excellence across all future race reports.
- **Differentiated AI Duality**: Orchestrated distinct prompt engineering pipelines for **Actual** vs **Predicted** reports. Pre-race forecasting now ingests `predictions.csv` (XGBoost/LightGBM) while post-race debriefs leverage high-fidelity FastF1 telemetry.
- **SDK Migration (Future-Proofing)**: Fully transitioned from `google.generativeai` to the modern `google.genai` SDK. This eliminates `FutureWarnings` and ensures long-term compatibility with Gemini 2.0+ models.
- **Mission-Critical Reliability**: Implemented `call_ai_with_retry` with exponential backoff (10s delay).
- **Engineering Fallback Personas**: Designed professional "Backup" narratives for cases where AI Quotas (429) are reached, maintaining a high-fidelity F1 Engineering persona instead of displaying raw technical errors.
- **Environment Optimization**: Purged 13 obsolete packages through `uv sync`, reducing environment overhead and improving CI/CD performance.

---

## v2.2.1 - Strategic Tyre Intelligence Overhaul
- **Proportional Stint Timeline**: Redesigned tyre bars as dynamic "loading bars" where width accurately reflects stint duration relative to total race laps.
- **Official Compound Colors**: Fixed pipeline mapping to ensure Soft (Red), Medium (Yellow), and Hard (White) compounds use official F1 broadcast colors.
- **Dynamic Circuit Scaling**: Implemented `total_laps` awareness, allowing the strategy timeline to scale accurately for any circuit distance.
- **High-Fidelity Visuals**: Added linear gradients, internal shadows, and interactive hover effects to strategy bars for a premium aesthetic.

---

## v2.2.0 - Professional F1 Broadcast Aesthetics & AI Stabilization
**Date**: May 2026

### 🌟 Major Highlights
- **Professional F1 Styling**: Implemented official team HEX color palette (Ferrari Rosso Corsa, McLaren Papaya, Mercedes Turquoise, etc.).
- **Teammate Differentiation**: Introduced `Solid vs Dashed` line styles to distinguish between drivers of the same team, mirrored in both the chart and the interactive legend.
- **Race Timeline Redesign**: Increased vertical resolution (480px) and implemented hierarchical focus logic (Top 10 focused, P11-P22 as elegant background filigree).
- **AI Narrative Fix**: Successfully stabilized the Gemini AI pipeline by implementing full model path resolution (`models/gemini-flash-latest`) and fallback mechanisms.

---

## v2.1.0 - Full Grid Telemetry & DNF Logic
**Date**: May 2026

### 🚀 Improvements
- **22-Driver Support**: Expanded the data pipeline and frontend visualization to support the full 2026 grid.
- **DNF "Drop" Visual**: Implemented specialized logic to visually "drop" retired drivers to P22, providing clear contextual attrition data without breaking chart continuity.
- **Hierarchical Data Architecture**: Migrated to a driver-centric JSON structure for optimized client-side rendering.

---

## v2.0.0 - MLOps Transformation
**Date**: April 2026

### 🏗️ Architecture
- **Next.js 15 Migration**: Rebuilt the dashboard using the latest Next.js 15 frameworks for superior performance.
- **Automated Pipeline**: Integrated `master_pipeline.py` for autonomous race data ingestion and AI reporting.
- **GitHub Actions Integration**: Full CI/CD for automated data updates and Vercel deployments.

---

## v1.0.0 - Initial Prototype
**Date**: March 2026

### 🏁 MVP
- **Baseline Models**: Initial XGBoost/LightGBM implementations for race pace prediction.
- **Static Reports**: Basic HTML exports of race simulations.
