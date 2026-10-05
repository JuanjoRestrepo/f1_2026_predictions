# F1 2026 Predictive Platform — End-to-End System Architecture

## Executive Architecture Summary

The **F1 2026 Predictive Platform** is an enterprise-grade data engineering, machine learning, and full-stack web application designed to forecast and analyze Formula 1 race performance hierarchies under the **2026 technical regulations**.

The system operates as an autonomous, event-driven pipeline that ingests telemetry, executes quantile regression models on a Databricks Lakehouse, registers champion model artifacts in Unity Catalog, generates structured LLM race briefings via Google Gemini, and deploys an interactive Next.js dashboard on Vercel.

```mermaid
flowchart TD
    subgraph Data Layer [1. Data Ingestion & Telemetry Transport]
        FastF1[FastF1 / Ergast API] --> |Raw Telemetry & Timing| Ingest[Ingestion Engine]
        Weather[Open-Meteo & External API] --> |Ambient & Wet Track Weather| Ingest
    end

    subgraph Databricks [2. Databricks Lakehouse & Delta Medallion]
        Ingest --> Bronze[(Bronze: telemetry_bronze)]
        Bronze --> Silver[(Silver: laps_silver)]
        Silver --> Gold[(Gold: driver_features_gold)]
    end

    subgraph ML Pipeline [3. Machine Learning & Stacking Suite]
        Gold --> Train[XGBoost + LightGBM + ExtraTrees Stacking]
        Train --> Dynamic[Dynamic Form EWMA Priors & Circuit Similarity]
        Train --> SHAP[SHAP Tree Explainability]
        Train --> UC[Unity Catalog Model Registry @champion]
    end

    subgraph Orchestration [4. Orchestration & Pre-Race Gate]
        Gate{is_race_window_active?}
        Gate --> |Race Weekend FRI-MON| Workflow[Databricks Lakeflow & GitHub Actions]
        Gate --> |Non-Race Day| Skip[Skip Execution / Conserve Compute]
    end

    subgraph Delivery & Security [5. Briefings, Dashboard & Security]
        Workflow --> Gemini[Google Gemini API]
        Gemini --> Briefings[Gmail SMTP & Discord Webhook Dispatch]
        Workflow --> Dashboard[Next.js 15 F1 TV Dashboard]
        Workflow --> Security[gh-secure: CodeQL + Dependabot + PVR]
    end
```

---


## 1. Telemetry Ingestion & Data Engineering Pipeline

### 1.1 Ingestion Sources
- **FastF1 Ergast API**: Synchronizes lap times, sector split times (S1, S2, S3), trap speeds, tyre compounds, stint lengths, pit stop durations, and telemetry channels (Throttle, Brake, RPM, Gear, Speed).
- **Open-Meteo Weather API**: Retrieves air temperature, track surface temperature, humidity, wind vectors, and rainfall indicators for circuit coordinates.
- **Cloud Cache Layer**: Caches raw FastF1 payloads in a local directory (`fastf1_cache/`) backed up to a Supabase S3 bucket for warm serverless execution.

### 1.2 Delta Medallion Architecture (Databricks DLT)
1. **Bronze Layer (`telemetry_bronze`)**: Raw, append-only ingestion of lap telemetry data preserving original data types.
2. **Silver Layer (`laps_silver`)**: Cleaned and validated dataset with Delta Live Tables (DLT) quality expectations:
   - `expect_or_drop("valid_laptime", "LapTime_s > 45 AND LapTime_s < 200")`: Removes pit-in/out out-laps and safety car anomalies.
   - `expect_or_fail("valid_driver", "Driver IS NOT NULL")`: Ensures strict entity integrity.
3. **Gold Layer (`driver_features_gold`)**: Feature matrix engineered per driver per stint:
   - Rolling 3-lap and 5-lap exponentially weighted moving averages (`roll_laptime_3`, `roll_laptime_5`).
   - Sector split performance ratios.
   - Tyre degradation rate ($\text{slope} = \Delta t / \text{lap}$).
   - Downforce and track abrasiveness encodings.

---

## 2. Machine Learning Modeling & Uncertainty Engine

### 2.1 Model Selection & Justification
In accordance with empirical benchmarks on tabular data (Grinsztajn et al., 2022), tree-based ensemble algorithms significantly outperform deep neural networks on structured telemetry features.

| Model | Purpose | Quantile / Objective |
|---|---|---|
| **XGBoost Regressor** | Primary lap pace baseline | `reg:squarederror` |
| **LightGBM Quantile Regressors** | Uncertainty bounds (P05, P50, P95) | `quantile` ($\alpha = 0.05, 0.50, 0.95$) |
| **Stacking Pace Regressor** | Ensemble meta-learner | Ridge Regression meta-estimator |

### 2.2 Cross-Track Baseline Pace Normalization
To translate season-wide driver pace to a specific circuit's physical lap time baseline:

$$\text{Driver\_Delta}_i = \text{Median}(\text{LapTime}_{i, \text{season}}) - \text{Median}(\text{LapTime}_{\text{global, season}})$$

$$\text{Target\_Pace}_{i, \text{track}} = \text{Baseline}_{\text{historical, track}} + \text{Driver\_Delta}_i$$

### 2.3 Chronological Validation (Leakage Prevention)
Models are trained exclusively on historical seasons with known outcomes (e.g. 2022–2025) and tested on unseen future seasons (2026), preventing temporal data leakage.

---

## 3. Automated Scheduling & Race Weekend Auto-Gate

### 3.1 Race Weekend Auto-Gate (`is_race_window_active()`)
To prevent unnecessary compute usage and spurious notification alerts:
- The system queries `calendar.json` (synced via `src/scripts/sync_calendar.py`).
- **Active Window**: Friday 00:00 UTC through Monday 23:59 UTC on scheduled race weekends.
- **Behavior**: If executed on a non-race day (e.g. Wednesday of a gap week), the pipeline logs a clean skip notification and terminates gracefully with exit code 0.
- **Override**: Passing `--force` CLI flag bypasses the gate for manual testing and CI/CD verification.

### 3.2 Databricks Lakehouse Workflow (`f1_2026_race_predictions_job`)
- **Schedule**: Quartz cron `0 0 6 ? * FRI-MON` (runs FRI-MON at 06:00 UTC).
- **Task 1 (`run_medallion_pipeline`)**: Executes DLT pipeline.
- **Task 2 (`train_and_register_champion`)**: Fits pace regressors, infers MLflow model signature (`infer_signature`), sets registry URI to `databricks-uc`, and promotes champion alias (`@champion`) in Unity Catalog schema `main.race_pace.xgb_race_pace_regressor`.
- **Task 3 (`dispatch_notifications`)**: Reads credentials securely via Databricks Secrets scope `f1_secrets` (`gmail_app_password`), sending HTML email briefings and Discord alerts via SMTP/Webhook.

### 3.3 GitHub Actions Scheduled Pipeline (`scheduled_sync.yml`)
- **Friday 18:00 UTC**: Pre-race prediction generation & briefing.
- **Monday 09:00 UTC**: Post-race telemetry audit, actual results processing, and automated git push to `master`.

---

## 4. Next.js Web Dashboard & Vercel Deployment

### 4.1 Rendering Strategy (SSG + ISR)
- **Static Site Generation (SSG)**: Pre-renders race pages at build time for instant global delivery via Vercel CDN.
- **Incremental Static Regeneration (ISR)**: Configured with `revalidate: 3600` (1 hour) to pick up new race artifacts without requiring full application rebuilds.

### 4.2 Available Race Discovery & Date-Gating (`getAvailableRaces`)
- **Pass 1**: Scans `reports/2026/summaries/` for `round_N` telemetry & report files.
- **Pass 2**: Scans `reports/2026/<race_dir>/results/predictions.csv`.
- **Date Guard**: Compares `race.isoDate` against current system time. Races scheduled in the future (e.g., Round 14 Spanish GP) remain **locked** until their scheduled race weekend arrives.

### 4.3 UI Component Hierarchy & State Management
- **Hero Card (`index.tsx`)**: Displays countdown timer to the current/next Grand Prix and links to the latest completed analysis.
- **Race Detail Page (`/race/[round]`)**:
  - **Metric Cards**: Predicted/Actual Winner, P2, and Fastest Lap. Automatically defaults to `"predicted"` mode when actual post-race results are pending.
  - **Race Timeline Chart (`RaceTimeline.tsx`)**: Canvas/Recharts visualization of lap-by-lap driver positions. Per-driver aggregation guarantees zero duplicate labels in the chart legend.
  - **Tyre Intelligence (`TyreIntelligence.tsx`)**: Visual breakdown of stint lengths, compounds (Hard/Medium/Soft), and pit stop windows.
  - **Finishing Order Table (`PredictionsTable.tsx`)**: Sortable classification grid with team color indicators and pace deltas.
  - **AI Race Analysis (`RaceReport.tsx`)**: High-impact markdown rendering of Google Gemini LLM briefings.

---

## 5. Security, Governance & Reliability

### 5.1 GitHub Security Lab Governance (`gh-secure`)
- **`SECURITY.md`**: Public vulnerability reporting policy and security disclosure protocol.
- **`dependabot.yml`**: Weekly automated dependency security updates for Python (`pip`/`uv`) and GitHub Actions.
- **`codeql.yml`**: Static security analysis pipeline for Python and GitHub Actions workflow files.
- **Branch Rulesets**: Active branch protection enforcing pull request reviews and status checks (`Require branches to be up to date before merging`).

### 5.2 LLM Fallback Chain (`call_ai_with_retry`)
1. **Primary Model**: `gemini-3.1-pro-preview` (high-reasoning narrative generation).
2. **Automated Fallback**: `gemini-3.5-flash` (triggered on quota exhaustion, 429 rate limits, or API outages).
3. **Deterministic Fallback**: Local structured template generator ensures valid markdown reports are published even during total upstream API outages.

### 5.3 Build Artifact Tracking (`.gitignore` Exceptions)
- Targeted git exceptions (`!reports/**/summaries/*.json`, `!reports/**/summaries/*.md`) ensure all generated telemetry files, lap timelines, tyre intelligence JSONs, and AI reports are tracked in version control and deployed to Vercel.

---

## 6. System Verification & Test Suite

The project enforces strict code quality and test coverage across the entire stack:

```bash
# Execute unit & integration test suite (279 tests across ML, cleaning, pipeline & AI)
uv run pytest

# Execute strict MyPy type check (0 issues across source files)
uv run mypy --strict src

# Execute Ruff code linter
uv run ruff check .

# Execute TypeScript type checker via pnpm (Zero-npm policy)
pnpm --filter dashboard exec tsc --noEmit

# Execute Next.js production build via pnpm
pnpm --filter dashboard run build
```

All 279 Python pytest modules pass with 100% line/branch coverage compliance, 0 type errors, and pnpm workspace verification.

