# 🗺️ F1 Prediction Roadmap: Towards "Full Reliability"

This document outlines the strategic technical evolution of the F1 2026 Predictive Platform, from its core ML engine to its fully automated deployment architecture.

---

## ✅ Phase 1: Contextual Intelligence (Track Features) [COMPLETED]
- **Track Characteristics DB**: Integrated metadata (Downforce, Abrasiveness, Full Throttle %) into the training matrix.
- **Integration Logic**: Model generalizes across similar track profiles (e.g., Jeddah and Miami).

## ✅ Phase 2: Statistical Rigor & Uncertainty [COMPLETED]
- **Quantile Regression**: Predicting optimistic (P05) and pessimistic (P95) lap times.
- **Temporal Decay**: Exponentially weighting recent race form for better predictive accuracy.

## ✅ Phase 3: Model Observability (DevOps Layer) [COMPLETED]
- **Post-Race Residual Analysis**: Automated calculation of MAE/MAPE against real results.
- **Feedback Loops**: Auto-triggering hyperparameter tuning based on error thresholds.

## ✅ Phase 4: Data Augmentation & 2026 Physics [COMPLETED]
- **Cross-Era Normalization**: Scaling historical data (2022-2025) to physically accurate 2026 performance levels.
- **Tire Degradation Modeling**: Integrating S/M/H compound deltas into the lap-time simulation.

---

## ✅ Phase 5: Interactive Full-Stack Dashboard [COMPLETED]
- **Next.js & Tailwind Implementation**: Created a premium, dark-mode dashboard inspired by F1 TV.
- **Dynamic Charting**: Position Chart (Recharts) allowing interactive lap-by-lap inspection.
- **AI Narrative Integration**: Gemini-powered race analysis based on ML artifacts.

## ✅ Phase 6: Tyre Intelligence & Strategy Strategy [COMPLETED]
- **Grid-wide Stint Visualization**: Interactive timeline showing tire strategy for all 22 drivers.
- **Business Question Engine**: Answering strategy efficacy questions (e.g., "Is M-H proven for Miami?").
- **Interactive Filtering**: Click-to-highlight and search logic for specific driver/team analysis.

## ✅ Phase 7: Multi-GP Scaling & Automation [COMPLETED]
- **Dynamic Routing**: Transformed the dashboard into a multi-race platform via `/race/[round]` routes.
- **Master Pipeline**: Created `master_pipeline.py` for one-click GP updates (Canada, Spain, etc.).
- **AI Reliability Layer**: Integrated professional Engineering Personas and dynamic GP-aware fallback logic for mission-critical dashboard stability.
- **CI/CD Automation**: GitHub Actions workflow for automated data ingestion and deployment.

---

## ✅ Phase 8: Industrialization & MLOps Inception [COMPLETED]
- **Inference Microservice**: Launched FastAPI backend for production lap-time predictions.
- **Multi-Arch CI/CD**: Automated parallel builds for Intel and Apple Silicon with manifest merging.
- **Strict Quality Gates**: Achieved 100% `mypy --strict` compliance and >80% test coverage.
- **Production Persistence**: Implemented `joblib` serialization for model versioning and immutable image builds.

---

## ✅ Phase 9: Automation & Proactive Intelligence [COMPLETED]
- **Automated Race Detection**: Event-driven pipeline triggers via FastF1 metadata (Monday 09:00 UTC).
- **Multi-Channel Notifications**: Strategic implementation of Gmail SMTP and Discord Webhooks for briefings.
- **Post-Race Verdict Engine**: Autonomous accuracy evaluation (MAE, Podium Accuracy) against real race results.
- **Premium Email Reporting**: Dark-mode, F1-branded HTML briefings with embedded Plotly charts.
- **Autonomous Autopilot**: Friday Pre-Race triggers for proactive strategy intelligence.

---

## ✅ Phase 10: Advanced Explainability & Precision [COMPLETED]
- **Weather Sensitivity**: Implemented high-fidelity weather timeseries integration for dynamic pace adjustment.
- **Advanced Explainability**: SHAP (Shapley Additive Explanations) integration for deep model reasoning.
- **SHAP-to-Text Narratives**: Automated translation of model feature impacts into professional race engineer insights.
- **HTML Engineering Reports**: Premium, F1-branded technical debriefs with integrated SHAP visualizations.

---

## ✅ Phase 11: Durable Agentic Orchestration [SUPERSEDED by Phase 17]
- **Durable Execution**: Migrated orchestration to **Trigger.dev v3** for 100% reliable, long-running race events.
- **Hybrid MLOps**: Integrated Node.js task management with a production-grade Python predictive engine.
- **Autonomous Autopilot**: Scheduled Friday forecasting and Monday auditing with automatic race discovery.
- **Fault-Tolerant Pipelines**: Resilience against network drops and API rate limits via durable retries.

> **Superseded (v6.4.0)**: Trigger.dev has been fully retired — the sources, configuration, CI job and SDK dependencies are gone. Durable execution now lives in the **Databricks Lakeflow job** (`f1_2026_race_predictions_job`), which is the single scheduler for the platform. See Phase 17.

---

## ✅ Phase 12: Advanced Modeling & Cloud Scalability [COMPLETED]
- **✅ Model Ensembling (Stacking)**: Implemented `StackingRegressor` (Bayesian Ridge meta-model on top of XGBoost and LightGBM) for improved lap pace precision.
- **✅ Dynamic Track Evolution**: Enhance "Track Evolution" logic using a *Rolling Track Grip* feature based on real-time parity deltas across the entire grid.
- **✅ External Weather Intelligence**: Integrated Visual Crossing/OpenWeather adapters for 7-day proactive rain probability, temperature, humidity, and wind context in Friday forecasts.
- **✅ Cloud Worker Deployment**: Dockerize the Trigger.dev worker for 24/7 serverless execution on AWS/GCP, eliminating local machine dependency.

## ✅ Phase 13: Human-in-the-Loop & Live Intelligence [COMPLETED]
- **✅ Waitpoint Approvals**: Implement Trigger.dev "Waitpoints" for race briefings, requiring engineer sign-off via Discord/API before final distribution.
- **✅ Live Timing Sockets**: Integrate real-time telemetry streams for "In-Race" pace re-calculation and strategic pivot alerts.
- **✅ Agentic Swarms**: Orchestrate specialized agents (Aero, Strategy, Weather) that coordinate via persistent state machines for multi-dimensional race insights.
- **✅ UI/UX Benchmark (Formula-Timer)**: Leverage **Formula-Timer** as a "design muse" for the Live Dashboard. While FastF1 remains the superior data engine, Formula-Timer's premium handling of latency, dynamic gaps, and micro-sector visualization will serve as the UX standard for Phase 13.

## ✅ Phase 14: Full-Stack Experience & Global Discovery [COMPLETED]
- **✅ Interactive Season Discovery (Home Page)**: Implemented dynamic 2026 race calendar, live countdowns to the next GP, and high-level performance trend cards.
- **✅ Historical Comparison Engine**: Side-by-side UI comparisons between different GP predictions to visualize model improvement and track-specific performance deltas.
- **✅ Dynamic Calendar Sync**: `sync_calendar.py` syncs FastF1 FIA event schedule to `calendar.json` with Vercel 404 guardrails.

## ✅ Phase 15: Databricks Lakehouse & Unity Catalog MLOps [COMPLETED]
- **✅ Databricks Asset Bundles (DABs)**: Production declarative bundle infrastructure (`databricks.yml`, `resources/jobs.yml`, `resources/pipelines.yml`) supporting `dev`, `staging`, and `prod` targets.
- **✅ Delta Live Tables (DLT) Medallion Architecture**: Automated Bronze (raw telemetry) → Silver (cleaned laps with quality expectations) → Gold (driver feature aggregates) streaming pipeline.
- **✅ Unity Catalog Model Registry & MLflow 3**: Model tracking and automated promotion to `@champion` / `@challenger` aliases in Unity Catalog (`f1_2026_dev.race_pace`).
- **✅ Databricks Serverless Execution**: Serverless Lakeflow workflow (`f1_2026_race_predictions_job`) completing end-to-end with 100% success. It has since grown to 5 tasks with a real telemetry ingest (Phase 17).

## ✅ Phase 16: Madrid GP, Dynamic Priors & Security Governance (`gh-secure`) [COMPLETED]
- **✅ Madrid GP Standalone Pipeline (`madrid_prediction_external.py`)**: Complete executable pipeline integrating FastF1 ETL, clean-air lap filtering, Bayesian shrinkage, and Stacking ML predictions.
- **✅ Unity Catalog Model Registry & Secrets (`@champion`)**: Verified model logging with `infer_signature` and `mlflow.set_registry_uri("databricks-uc")` under `main.race_pace.xgb_race_pace_regressor@champion`, using Databricks secret scope `f1_secrets` (`gmail_app_password`).
- **✅ Dynamic Form-Based Priors (`compute_dynamic_form_priors()`)**: Dynamic EWMA prior calculation auto-updating from actual race JSON summaries.
- **✅ Circuit Similarity Transfer Learning (`compute_circuit_similarity()`)**: Multi-dimensional layout vector matching for new circuit baseline estimation.
- **✅ Rain-Adjusted Pace Engine (`add_wet_race_pace_penalty()`)**: Wet-surface penalty and rain intensity index for mixed-condition races (Sepang).
- **✅ Ensemble Stacking Expansion**: Integrated `ExtraTreesRegressor` (and optional `CatBoostRegressor`) as 3rd base learner.
- **✅ GitHub Security Lab Governance (`gh-secure`)**: Integrated Private Vulnerability Reporting (`SECURITY.md`), Dependabot automated security updates (`dependabot.yml`), and CodeQL static analysis (`codeql.yml`).

## ✅ Phase 17: Single-Orchestrator Consolidation & Dashboard Serving [COMPLETED]
- **✅ Trigger.dev Retired**: Removed the Trigger.dev sources, configuration, CI job and SDK dependencies; the Databricks Lakeflow job is now the single scheduler for the whole platform.
- **✅ GitHub Actions Race Cron Removed**: `scheduled_sync.yml` is retained purely as a manual `workflow_dispatch` fallback, while `sync_calendar.yml` keeps its calendar cron.
- **✅ Real Telemetry Loop**: `ingest_race_telemetry` lands completed-round FastF1 laps in the Unity Catalog `raw_telemetry` Volume and `telemetry_bronze` tails it with Auto Loader, closing the cloud self-learning loop (Bronze → Silver → Gold → retrain).
- **✅ Champion Promotion Gate**: `@champion` is only re-tagged when the candidate beats the incumbent's cross-validated RMSE (`F1_PROMOTION_TOLERANCE` as an escape hatch), preventing silent model regressions.
- **✅ Dashboard Data Serving**: `export_dashboard_data` publishes `reports/<season>/**` to object storage under `dashboard/<season>/` (manifest written last); the dashboard `prebuild` puller consumes it, with the committed `reports/**` tree as the fallback.
- **✅ Honest Reporting**: Post-race verdicts emit explicit `preview` / `partial` / `unavailable` statuses instead of unmeasured accuracy claims.
- **✅ Supply-Chain Hardening**: Every open CodeQL alert cleared, all GitHub Actions moved to Node 24 runtimes, and `CONTRIBUTING.md` added to document the trunk-based branch model.

---

## ✅ Phase 18: Pace & Telemetry Normalization, Availability Guard & DABs Structural CI [COMPLETED]
- **✅ Circuit-Relative Pace Normalization**: Replaced pooled season medians with round-relative reduction so track mix no longer contaminates driver deltas (field spread reduced from 13.55s down to 4.90s physical baseline).
- **✅ Sector & Speed Track Normalization**: Sector deviations scaled by the circuit lap-time ratio $r$ and speed deltas in km/h, preventing a 12–16× artificial spread inflation.
- **✅ Dispersion Tripwire Check**: Added `check_published_dispersion()` with a 1.25× tripwire comparing published spread against lap-measured spread.
- **✅ Calendar Availability Guard**: `scripts/check_next_race_coverage.py` mirrors the UI's availability rule in Python and fails loudly in `sync_calendar.yml` when an upcoming race cannot be rendered.
- **✅ DABs Structural CI Validator**: Added `scripts/validate_bundle.py` verifying bundle syntax, task environments, and substitutions in PR CI without requiring Databricks credentials.
- **✅ Manual Sync Credentials Hardening**: Repaired `scheduled_sync.yml` secrets mapping and added visible `::warning::` annotations for missing credentials.
- **✅ Docker Cross-Build & Smoke Test**: Cross-compilation via `uv sync --python-platform` on `$BUILDPLATFORM` without QEMU emulation, non-root directory ownership fix, and digest `/health` smoke-testing.
- **✅ Supabase S3 Key Rotation**: Added `scripts/rotate_supabase_s3_keys.py` and runbook documenting the two live credential locations.

---

## ✅ Phase 19: Physical Traffic Exposure Modeling & Clean-Air Serving Manifold [COMPLETED]
- **✅ Measured Traffic Exposure Features**: Reconstructed on-track intervals across 77,696 laps (`features/traffic_exposure.py`) to label `traffic_ahead_s`, `traffic_nearest_s`, and `in_clean_air`.
- **✅ Empirical Dirty Air Validation**: Measured the dirty-air penalty decay (+0.571s at <0.5s to noise floor at 2.0s) independently of label definitions.
- **✅ Multi-Season Held-Out Ablation**: Demonstrated lap-level MAE reduction across 2024–2026 on traffic-affected laps while within-round placebo held at zero.
- **✅ Clean-Air Virtual Scenario Serving**: Simulator serves virtual laps with measured clean-air medians (5.0s ahead, 3.0s nearest), sitting cleanly inside the trained feature manifold rather than the missing-value branch.
- **✅ Refuted Sub-optimal Alternatives**: Refuted training pace solely on clean-air laps (which degraded published rank correlation from 0.554 to 0.500) and excluded redundant `in_clean_air` boolean from model features.

---

## ✅ Phase 20: Model-Lifecycle Governance & Honest Feature Ablation [COMPLETED]
- **✅ Architecture Map & Model Clarification**: Documented the 3 model lanes (Registry champion, Race simulation, Serving container), the 2 Gold schemas, and the status of known gaps in `ARCHITECTURE.md` §3.4.
- **✅ DLT Gold Feature Gap Closed**: Emitted `tyre_degradation_slope` (`regr_slope`) in `f1_medallion_pipeline.py` and made `run_train` raise `ValueError` on any missing named feature.
- **✅ FastAPI Serving Artifact Refreshed**: Rebuilt `xgb_pace_model.joblib` with 70 features (including traffic margins) and sidecar `xgb_pace_model.metadata.json`, enforced by unit test.
- **✅ Stacking Metric History Regenerated**: Added missing `stacking` entries to historical `metrics.json` files.
- **✅ Walk-Forward Temporal Isolation**: Added `_gold_files_before_round` to `simulate_race.py` to prevent backtest replays from reading target-round answers.
- **✅ Measured & Rejected 22-Column Rebuild**: Paired 5-seed ablation on 74,601 common laps showed extra circuit and state columns degraded generalization, keeping published Gold schema clean and intentional.

---

## 🚀 Phase 21: Pre-Lap Causal Modeling & Feature Parity [ACTIVE]
- **✅ Task 21.1: Resolve One-Hot Simulation Skew [COMPLETED]**:
  - Populated one-hot dummy columns (`Compound_*`, `Team_*`, `EventName_*`) in `simulate_race.py` via `_align_scenario_one_hot_features()`, eliminating 45 NaN dummy features (~1,000 NaN cells per scenario) from the simulation scenario vector.
  - Benchmarked across multi-round backtests (2025 R22–R24, 2026 R02, R03, R18): mean rank correlation improved from 0.6069 to 0.6161 (Las Vegas: 0.6718 → 0.6904; Abu Dhabi: 0.4872 → 0.5113), with published field spread remaining within dispersion tripwires.
- **✅ Task 21.2: Eliminate Lap-Level Target Leakage [COMPLETED]**:
  - *Implementation*: Applied a strict pre-lap causal (t-1) boundary to `rolling_pace.py`. `add_rolling_pace_features()` now uses `.shift(1)` before each rolling window so `roll_laptime_3/5` and `roll_std_3` reflect only the *N* completed prior laps. `add_lap_delta_to_fastest()` replaced the full-group session minimum with `.shift(1).expanding().min()` so `delta_to_fastest_s` reflects the best *prior* lap.
  - *Semantic consequence*: Lap 1 in each (Driver, Stint) group now returns NaN for rolling features — XGBoost routes these to its trained missing-value branch. `delta_to_fastest_s` for Lap 1 is also NaN. All 8 rolling-pace unit tests updated to encode the new causal contract (460 passing).
  - *Metric context*: The ~0.2 s published MAE was a reconstruction metric. Post-fix MAE from a chronological walk-forward pass is the honest estimate; this is the baseline for all future model iterations.
- **✅ Task 21.3: Bridge DLT Gold and Local Feature Schemas [COMPLETED — implemented; materialised in dev, staging, and production]**:
  - *Shared contract*: `features/contract.py` (v1) defines the keys, target `LapTime_s`, 13 pre-lap-safe lap features, the legacy aggregate preset, and a version stamp. `features/training_data.py` enforces it and preserves the different NaN policies: `fillna(0.0)` only for the aggregate lane, native missing values for lap rolling features.
  - *DLT*: New `lap_features_gold` table built by `databricks/pipelines/lap_features.py` with causal Spark windows (3/5-lap means ending at t−1, two-prior-lap std minimum, prior-best delta, compound indicators). Bronze/Silver now carry `Stint`, `Team` and `Position`; Silver exposes `RoundNumber`; both Gold tables filter to race sessions.
  - *Training/serving*: `--training-schema lap` selects the new lane, uses event-grouped `GroupKFold` instead of a leaky lap split, and registers `xgb_lap_pace_regressor` under its own `@champion` alias. `--run-mode predict` writes `<table>_predictions`. The aggregate champion and scheduled export job are unchanged.
  - *Excluded on purpose*: `Position` (end-of-lap), `tyre_deg_slope`/`tyre_life_norm` (full-stint, prospective), and local-only telemetry/form/weather/team/event features. The local 70-feature model keeps them; the bridge does not claim they are pre-lap safe.
  - *Validated*: 485 tests pass; Spark 4.2 parity against the Pandas reference on a two-event synthetic frame. Cloud full refreshes in dev, staging, and production materialised 93,381 Bronze laps, 93,364 Silver laps, 1,679 driver rows (25 events, 2022–2026, 1,671 non-null `tyre_degradation_slope`) and 92,807 lap rows at contract v1. The opt-in lap model remains untrained; the production aggregate lane was trained in Task 21.4, and no published R18 report was regenerated.
- **✅ Task 21.4: Production DABs Bundle Deployment [COMPLETED]**:
  - *Context*: Updated bundle definitions include `tyre_degradation_slope` and `lap_features_gold`.
  - *Deployed*: Dev, staging, and production targets are deployed and full-refreshed. Production uses `main.f1_2026_prod`; its schedule is now `UNPAUSED` (Fri–Mon 06:00 UTC). Staging/prod use dedicated schemas because the workspace metastore has no default storage root for standalone catalogs.
  - *Fixes found by cloud validation*: Replaced Unity Catalog-incompatible `input_file_name()` with `_metadata.file_path`; repaired the seeded Volume from 35-column raw FastF1 frames (including `TIMESTAMP(NANOS)` columns Spark cannot read) onto the 12-column Bronze contract; dropped stale dev materialisations so Bronze could become a streaming table.
  - *Production refresh verified*: Update `64357528-0889-4814-b792-29427c011930` completed with the same 93,381 Bronze / 93,364 Silver / 1,679 driver / 92,807 lap rows as dev and staging.
  - *Production job verified*: Manual run `1044964739853858` passed all five tasks (ingest, DLT, train, notify, export). The aggregate lane trained on 1,679 rows × 4 features with 3-fold CV RMSE **1.6566 ± 0.3404** (MLflow run `4729a835c2c74a64bfdac65490aa9c47`) and registered `main.f1_2026_prod.xgb_race_pace_regressor` v1 as `@champion` — the first version in the previously empty production registry. The opt-in `xgb_lap_pace_regressor` was **not** trained.
  - *Side effects*: Export published 194 dashboard artifacts plus `manifest.json` and triggered the dashboard rebuild (HTTP 201). The notify task completed, but Gmail SMTP failed (`0/1 channels succeeded`), so no production email was delivered; Discord is not configured.
  - *Old alert*: The user-visible failure `23e4377c` at 01:06 UTC was the legacy Volume schema error. It is superseded by the Volume repair and the successful dev refresh `dd2f294b`; it was not a regression from this deployment.
  - *Not changed*: No R18 report was regenerated and no existing dev/local aggregate champion was replaced. The production champion is a new first version in an empty registry.

---

## 📝 Strategic Technical Notes
- **FastF1 vs. Formula-Timer**: The platform will continue using FastF1 as the "Ground Truth" for ML modeling and telemetry analysis. Formula-Timer is designated as a secondary-screen validation tool and UI reference to ensure professional-grade visualization and real-time trend benchmarking.
- **Model Target**: Maintain a target MAE < 0.150s through iterative Stacking (Phase 12-16) and strict causal feature separation (Phase 21).



