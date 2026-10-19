# F1 2026 Predictions - Release Notes

## [v6.7.0] - 2026-10-18
### 🌉 A Versioned Lap-Level Bridge Between DLT and Local Features (Task 21.3)
- **Feature**: `features/contract.py` defines a shared, versioned, pre-lap-safe feature set (v1, 13 columns) plus two training presets: the existing per-driver `aggregate` lane and a new `lap` lane targeting `LapTime_s`. The contract is the same object used by the DLT table and the local validation test — not a second copy of the feature names.
- **Feature**: The DLT pipeline now emits `lap_features_gold` (per lap, race sessions only). `databricks/pipelines/lap_features.py` mirrors the local causal semantics with Spark windows: 3/5-lap rolling means ending at the previous lap, a 3-lap sample standard deviation with a two-prior-lap minimum, `delta_roll_pace`, a cumulative prior-best `delta_to_fastest_s`, and five compound indicators. The local Spark 4.2 test compares it row for row with the Pandas reference across two synthetic events, including first-lap NaNs and cross-event isolation.
- **Feature**: `run_train --training-schema lap` trains `xgb_lap_pace_regressor` with event-grouped `GroupKFold`, leaves missing rolling features as NaN for XGBoost's native missing branch, and keeps its `@champion` alias separate from `xgb_race_pace_regressor`. The aggregate lane keeps its historical 3-fold CV and `fillna(0.0)` behaviour.
- **Feature**: `run_predict --training-schema lap` scores a Gold table with the schema's `@champion` and writes `<table>_predictions` (keys, prediction, model name, UTC timestamp). It is a manual mode; the scheduled job still exports rather than predicts.
- **Data**: Bronze/Silver now carry `Stint`, `Team` and `Position`, and Silver exposes `RoundNumber` (previously dropped before Gold). Both DLT Gold tables filter to `SessionType == "Race"` so sprint/qualifying laps cannot enter driver aggregates.
- **Deliberately excluded**: `Position` (FastF1 assigns it after the lap is complete), `tyre_deg_slope` and `tyre_life_norm` (both fit the whole stint, including future laps), and sector/speed/pit/traffic/form/team/event columns that are post-lap or local-only. The local 70-feature model is unchanged; this contract does not endorse those columns as pre-lap features.
- **Validated locally**: 485 tests pass, including the Spark/Pandas parity test; `ruff check`, `ruff format --check` and `mypy src/ --strict` are clean. The local Gold snapshot still predates the 21.2 causal fix; the parity test validates the Spark transform against the Pandas reference, not a rebuilt local file.
- **Validated in the cloud (dev and staging)**: Full refreshes materialised 93,381 Bronze laps, 93,364 Silver laps, 1,679 driver rows (25 events, 2022–2026; 1,671 non-null `tyre_degradation_slope`) and 92,807 rows in `lap_features_gold` at contract v1. This confirms the new table and the refreshed aggregate schema, not a new model: the lap model is not trained or registered, and no published report or aggregate champion was changed.
- **Cloud deployment fixes**: The production and staging targets now use dedicated schemas (`main.f1_2026_staging`, `main.f1_2026_prod`) because the workspace metastore has no default storage root for standalone catalogs. Unity Catalog rejected `input_file_name()` in the Bronze stream, so the pipeline now uses `_metadata.file_path`. The seeded Volume contained 35-column raw FastF1 frames with `TIMESTAMP(NANOS)` columns Spark cannot read; it was rebuilt onto the 12-column Bronze contract, and stale dev materialisations were dropped so Bronze could be recreated as a streaming table.
- **Blocked at production materialisation**: The `prod` bundle is deployed with its schedule paused. Its first full refresh failed twice at cluster creation with `RESOURCE_EXHAUSTED: You've hit the limit for serverless compute for free usage`; stopping the idle dev/staging pipelines did not release the workspace-level cap. The scheduled job, aggregate champion training and notifications have not run.

---

## [v6.6.1] - 2026-10-18
### 🔧 Model-Lifecycle Gaps Closed — and a Rebuild Measured Rather Than Assumed
- **Fix**: The registry champion no longer silently trains on three of its four named features. The DLT Gold table now emits `tyre_degradation_slope` (`regr_slope(LapTimeSeconds, LapNumber)`), and `run_train` raises when a named feature is absent instead of filtering the survivors and proceeding.
- **Fix**: The FastAPI serving artifact is refreshed from the current Gold layer (2022–2025, 77,696 laps, 70 features including both traffic margins) and now ships with `xgb_pace_model.metadata.json`; `tests/unit/test_serving_artifact.py` keeps the sidecar and the binary in agreement. It remains a snapshot, and it is still not the model behind any published prediction.
- **Fix**: The stale `metrics.json` files now carry the `stacking` entry alongside `xgboost` and `lightgbm` — 2026 season (stacking MAE 0.201 s), 2026 Japanese GP and 2024 Miami.
- **Measured, not adopted**: A full local Gold rebuild now recovers real event names (circuit profiles), results-derived form and weather, adding 22 columns and dropping 3,022 safety-car/VSC laps. A paired 5-seed ablation on the 74,601 common laps found no robust gain: removing the four state columns *lowered* held-out MAE by 0.021/0.018/0.025 s across 2024–2026, and removing the seven circuit columns by 0.067/0.014/0.048 s; weather and form changed sign by season, and the old frame beat the rebuilt one in 2024, lost in 2025 and tied in 2026. The published Gold stays at its original schema; the corrected `scripts/rebuild_data.py` is kept for a future, feature-by-feature adoption.
- **Recorded, not fixed**: The simulator's scenario rows were all-NaN across every encoded compound/team/event column. Correcting that skew was neutral in a controlled replay of 2025 R22 (rank correlation 0.709 → 0.728, centred MAE 0.322 → 0.320 s), so the change was reverted rather than shipped on single-round evidence.
- **Recorded, not fixed**: `roll_laptime_3/5`, `delta_to_fastest_s`, `tyre_deg_slope` and the sector/speed columns are derived from the current lap, the whole stint or the session minimum, so the ~0.2 s MAE is a reconstruction error, not an out-of-sample race-prediction error. §2.4 and §3.4 now say so explicitly.
- **Fix**: The simulator's backtest window now excludes the round being predicted (`_gold_files_before_round`), so a walk-forward replay cannot read the answer; a unit test pins the boundary.

---

## [v6.6.0] - 2026-10-17
### 🌬️ Traffic Exposure Measured from Every Race Lap
- **Feature**: Every Gold lap now carries measured traffic-exposure labels — `traffic_ahead_s`, `traffic_nearest_s` and `in_clean_air` — reconstructed from all cars' on-track intervals (`features/traffic_exposure.py`, feature-pipeline step 7b) and backfilled across all 86 rounds. 77,659 of 77,696 laps (99.95%) are labelled, 44.0% of them clean. The two margins are model features; the flag stays in Gold as a measurement label and is excluded from every feature matrix.
- **Feature**: The simulator serves its unraced lap as a clean-air lap, using the measured clean-air medians (5.0 s ahead, 3.0 s nearest), so scenario rows sit inside the region the trees were trained on instead of on their missing-value branch.
- **Validated**: The estimator reproduces the dirty-air penalty it claims to measure, independently of the label definition: +0.571 s under 0.5 s behind, +0.291 s at 0.5–1.0 s, +0.092 s at 1.0–1.5 s, +0.013 s beyond 1.5 s (paired within driver-stint, tyre age matched). The penalty decays monotonically to the noise floor at the 2.0 s threshold, which is where clean air was set — measured, not assumed. A fixed 101 s reference would have misclassified 4,272 laps (5.5%), with 39 of 86 rounds above 5%; the session median moves labels by at most 0.0054 s against an independent estimator.
- **Measured**: Ablated on three held-out seasons, paired across 10 seeds against a within-round placebo, the two margins reduce lap-time MAE in every season (2024 −0.0092 s, 2025 −0.0164 s, 2026 −0.0095 s; on clean-air laps −0.0059/−0.0121/−0.0058 s) while the placebo stays at zero. The gain is modest and concentrated on traffic-affected laps (−0.0120/−0.0195/−0.0116 s), the mechanism the labels encode. Walking the simulator forward over five completed rounds, rank agreement improved in all five against the pre-change model (mean Spearman +0.047) and centred error in four of five (+0.008 s).
- **Refuted**: Measuring driver pace from clean-air laps only improved the average delta error (0.596 s vs 0.624 s) but degraded the ordering the product publishes (rank correlation 0.554 → 0.500, worse in 8 of 10 rounds).
- **Why the flag is not a feature**: `in_clean_air` is exactly the two thresholds applied to the two margins, so it adds no information; ablated alongside them it made every season worse (2025: −0.0117 s with it vs −0.0164 s without).
- **Changed**: Round 18 is regenerated with the shipped model: published spread 5.093 s against a lap-measured 4.897 s (1.04×, inside the 1.25 tripwire). The P50 path improves against both the all-lap and the clean-air references; the xgb path is unchanged against the clean-air reference (0.8859 → 0.8858) and slips slightly against the all-lap one, which is the mismatched benchmark for a clean-air lap.
- **Verified**: Regenerating Gold through the new pipeline step reproduces the backfilled labels exactly (0 differing labels across rounds spanning 2022–2026), and the served feature set matches the trained one.
- **Docs**: `ARCHITECTURE.md` §2.3 documents the labels, their validation and the ablation; chronological validation moves to §2.4.

---

## [v6.5.0] - 2026-10-17
### 📐 Model Dispersion Measured from Laps, and a Container That Actually Runs
- **Fix**: The model no longer publishes a field spread its own laps contradict. `Sector1Time_s`–`Sector3Time_s` and `SpeedI1`–`SpeedST` reached the model as per-driver season medians pooled across a window that mixes circuits 13s apart, so their cross-driver spread mostly measured *which* circuits each driver had laps at — 12.0× the per-circuit spread for `Sector2Time_s` and 16.4× for `Sector3Time_s`, against 2.8× for lap time. Every driver-specific deviation is now re-measured per circuit, exactly as the lap-time path already does. Round 18: field spread 6.465s → 4.920s against a lap-measured 4.897s, correlation with measured pace 0.946 → 0.988, residual std 0.502s → 0.215s. Runs remain byte-for-byte reproducible.
- **Fix**: The published container image could not start. `COPY` layers materialise their destination directories as root, so `/app` was root-owned, `f1user` could not create `/app/.cache`, and uvicorn died with `PermissionError` before binding a port — and nothing ran the image, so it went unnoticed. Runtime directories are now scaffolded and owned after every `COPY`.
- **Fix**: Removed `clean_air_pace_delta_s` and `clean_air_confidence` from the simulation scenario. They existed in none of the 77,696 training rows, so no tree could split on them; zeroing them left predictions byte-identical. That is train/serve skew, not signal — the curated prior keeps its real job in the clean-air pace module.
- **Added**: `check_published_dispersion()` compares the spread about to be published against the lap-measured one and warns above 1.25× (it reads 1.32× on the old behaviour, 1.00× after). The Docker workflow now smoke-tests each platform's image by digest, requiring `GET /health` to answer `200` with the model loaded.
- **Changed**: Container images publish on version tags only. A push to `master` fired a build that the tag then duplicated — identical bytes twice per release for ~7 minutes of runner time. The dependency stage is now cross-built with `uv sync --python-platform`, taking the `arm64` leg from 528s to 232s with no emulation.
- **Docs**: `ARCHITECTURE.md` §2.2 now states the normalisation actually implemented — the pooled-median formula it described had been superseded — with the measured inflation table, and §5.4 records what the container artifact is and that nothing automated consumes it.

---

## [v6.4.1] - 2026-10-17
### 🎯 Pace-Normalisation Correctness, an Honest CI Gate & Credential Hygiene
- **Fix**: Driver pace is now measured per circuit (`scripts/simulate_race.py`). The simulator subtracted a season median pooled across every circuit in the window, which mostly measured *which* tracks a driver had laps at — the window mixes circuits 13s apart, so 52–54% of some drivers' laps came from a short circuit and inflated them by 6–8s. Each lap is now referenced to its own round's baseline, reduced to one observation per round, and sector times follow the window-to-track ratio. Driver delta spread for round 18: 13.554s → 4.897s.
- **Fix**: `Validate DABs Bundle` now validates. It exited 0 whenever `DATABRICKS_HOST` was unset, and since the secret was never configured it had validated nothing since it was added, leaving the bundle checked only at `bundle deploy` time. `scripts/validate_bundle.py` now decides everything that needs no workspace (YAML validity, include targets, in-bundle file references, `environment_key`/`depends_on` integrity, `${var.*}` / `${resources.*}` substitutions, `resources:` typos) on every pull request, and `databricks bundle validate` activates by itself once credentials exist.
- **Fix**: The manual `scheduled_sync.yml` fallback asked for `secrets.F1_GEMINI_API_KEY` while the repository secret is `GEMINI_API_KEY`; because a present-but-empty env var beats the config's alias, every manual run silently produced non-AI narratives. It also built zero notification channels and exited 0 — a green run that briefed nobody. The name is corrected, the missing secrets are set, and a credential check now annotates the run page with `::warning::` for anything still absent.
- **Fix**: The next-race availability guard (`scripts/check_next_race_coverage.py`) fails loudly in the weekly `sync_calendar.yml` workflow when the upcoming race cannot be rendered, instead of the dashboard quietly greying it out.
- **Changed**: `scripts/rotate_supabase_s3_keys.py` rotates the Supabase S3 pair across `.env` and the Databricks `f1_secrets` scope, with the runbook in `CONTRIBUTING.md` recording that the pair lives in exactly two places.
- **Security**: Rotated the Supabase S3 key pair (the retired pair now returns HTTP 403, verified against the bucket), documented the rotation runbook and the fact that the pair lives in exactly two places, and removed the retired keys, the five stale GitHub Actions secrets and the local `.env.bak.*` backups that held them.
- **Docs**: `ARCHITECTURE.md` §4.1/§4.2 corrected to the serving path actually in use, and §3.3 now records that the Actions fallback keeps its own credential store; `CONTRIBUTING.md` distinguishes the two bundle checks.

---

## [v6.4.0] - 2026-10-17
### Single-Orchestrator Consolidation, Databricks → Dashboard Serving & Supply-Chain Hardening

#### ☁️ Databricks → Dashboard Serving Path
- **`--run-mode export`**: `run_export()` collects the season's `reports/<season>/**` artifacts, discovers the completed rounds, and publishes them to S3-compatible storage under `dashboard/<season>/`, writing `manifest.json` **last** as the completeness signal (`src/f1_predictions/utils/dashboard_publish.py`).
- **`export_dashboard_data` Lakeflow task**: runs in parallel with `dispatch_notifications` after training, so the dashboard refreshes straight from the lakehouse with no GitHub Actions race cron.
- **`dashboard/scripts/fetch-dashboard-data.mjs`**: new dashboard `prebuild` puller. Opt-in via `F1_DASHBOARD_DATA_BASE_URL`; it never breaks the build unless `F1_DASHBOARD_DATA_STRICT=1`, and it refuses path traversal. The committed `reports/**` tree remains the fallback.
- **`get_s3_client()`**: promoted to a public accessor in `cloud_cache.py` and reused by the publisher (`SUPABASE_S3_*` configuration).

#### 🔄 Real Telemetry: FastF1 → Unity Catalog Volume → DLT Bronze
- **`run_ingest()` / `volume_ingest.py`**: completed-round FastF1 laps are landed in the Unity Catalog `raw_telemetry` Volume through a pure, unit-testable transform.
- **`telemetry_bronze` Auto Loader**: the medallion pipeline now tails the Volume with Auto Loader instead of sample data, so real laps flow Bronze → Silver → Gold.
- **Missing lap timing is non-fatal**: when a timing environment cannot supply lap data the round is skipped and post-race verdicts degrade to a positional-only `partial` status instead of fabricating accuracy.

#### 🏆 Champion Promotion Gate
- **`should_promote()` / `get_champion_metric()`**: `@champion` is only re-tagged when the candidate improves the incumbent's cross-validated RMSE. `F1_PROMOTION_TOLERANCE` provides an escape hatch.

#### 🗓️ Single Scheduler (Trigger.dev Retired)
- **Trigger.dev decommissioned**: removed the sources, configuration, CI job and SDK dependencies — the Databricks Lakeflow job is now the single scheduler.
- **GitHub Actions race cron removed**: `scheduled_sync.yml` remains as a manual `workflow_dispatch` fallback while `sync_calendar.yml` keeps its calendar cron.
- **Job graph**: `ingest_race_telemetry` → `run_medallion_pipeline` → `train_and_register_champion` → (`dispatch_notifications` ∥ `export_dashboard_data`).

#### 🔒 Security & Supply-Chain Hardening
- **CodeQL clean**: every open alert cleared rather than suppressed — clear-text logging of API keys and coordinates, unused globals/imports, `Protocol` bodies, and a latent `NameError` in `scripts/master_pipeline.py`.
- **GitHub Actions on Node 24**: `upload-artifact` v4 → v7, `download-artifact` v4 → v8, `setup-buildx-action` v3 → v4, plus the Dependabot batch (`checkout` v7, `setup-python` v7, `cache` v6, `codeql-action` v4, `setup-qemu-action` v4, `login-action` v4, `metadata-action` v6, `build-push-action` v7). `astral-sh/setup-uv` is pinned to `v10.3.0` because upstream no longer publishes floating major tags past `v7`.
- **`CONTRIBUTING.md`**: documents the trunk-based branch model, the `master` protections, the PR flow, the pre-push checklist, the secrets rule and the action-pinning convention.

#### 🔧 Fixes
- **Honest verdicts**: post-race accuracy is only reported when it is actually measured; otherwise the report emits explicit `preview` / `partial` / `unavailable` statuses.
- **Uncertainty bounds**: consolidated into a shared `ensure_uncertainty_bounds` helper so predicted/actual bounds synthesis cannot drift between code paths.

---

## [v6.3.0] - 2026-10-04
### Madrid GP External Integration, Dynamic Priors, Unity Catalog Model Registry & GitHub Security (`gh-secure`)

#### 🇪🇸 Madrid GP & FastF1 Standalone Prediction Pipeline
- **`scripts/madrid_prediction_external.py`**: Completed, syntax-error-free executable implementation of Madrid GP predictions integrating FastF1 ETL, clean-air lap filtering, Bayesian shrinkage, and Stacking ML inference (`XGBRegressor` + `Ridge`).
- **Telemetry Data Ingestion**: FastF1 ingestion across Rounds 1–13 (286 driver-race instances) cached to `data/fastf1_2026_pre_madrid.csv`.

#### ⚡ Databricks Unity Catalog Model Registry (`@champion`) & Secrets Scope
- **Unity Catalog Model Registration**: Verified full model lifecycle in `main.race_pace.xgb_race_pace_regressor` logged with `infer_signature(X, y_pred)` and `mlflow.set_registry_uri("databricks-uc")`. Version 1 successfully tagged with **`@champion`** alias.
- **Databricks Secrets Integration**: Secret scope `f1_secrets` created with key `gmail_app_password` set via Databricks SDK.
- **Live Email Verification**: Verified end-to-end briefing dispatch to `restrepojuanjo@gmail.com` with MAE 0.178s accuracy and P1 Antonelli winner prediction.

#### 📊 Dynamic Priors & Circuit Transfer Learning
- **Dynamic Form Priors (`compute_dynamic_form_priors()`)**: Replaced static pre-season assumptions with auto-updating EWMA driver form deltas computed dynamically from actual race summaries (`reports/2026/summaries/actual_results_round_*.json`).
- **Circuit Similarity Engine (`compute_circuit_similarity()`)**: Added normalized multi-dimensional layout similarity index (`streetness`, `speed_bias`, `overtaking_ease`, `tyre_stress`, `overtake_difficulty`, `safety_car_probability`) for transfer learning on new/semi-street venues.
- **Wet-Race Penalty (`add_wet_race_pace_penalty()`)**: Engineered `rain_intensity_index` and `wet_pace_penalty_s` for mixed/wet condition modeling (relocated Round 16 Sepang GP).
- **Ensemble Stacking Refinement**: Added `ExtraTreesRegressor` (and optional `CatBoostRegressor` dynamic loading) as 3rd base learner in `StackingPaceRegressor`.
- **Rounds 15 & 16 Actual Results**: Created `actual_results_round_15.json` (Baku: RUS winner) and `actual_results_round_16.json` (Sepang: VER winner wet-dry race), with `HAD` (Hadjar) driver support.

#### 🔒 GitHub Security Lab Governance (`gh-secure`)
- **`SECURITY.md`**: Added Private Vulnerability Reporting policy and security advisory instructions.
- **`dependabot.yml`**: Enabled weekly automated dependency scanning for Python (`pip`/`uv`) and GitHub Actions.
- **`codeql.yml`**: Added CodeQL static security analysis workflow for python and actions code scanning.

---

## [v6.2.1] - 2026-08-23

### Dutch GP (Round 12) Pre-Race Simulation & Intelligence Release

#### 🇳🇱 Dutch GP Predictive Coverage
- **Simulated Pace Hierarchy**: Generated LightGBM quantile regression predictions for Round 12 (`Dutch_Grand_Prix/results/predictions.csv`).
- **Predicted AI Report**: Generated `predicted_report_round_12.md` featuring Executive Summary, Top 10 Pace Table, and 1-stop Medium → Hard strategy window.
- **Race Timeline & Tyre Intelligence**: Created `predicted_lap_positions_round_12.json` and `predicted_tyre_intelligence_round_12.json`.

---

## [v6.2.0] - 2026-08-23
### Complete Dashboard Telemetry & AI Intelligence Upgrade

#### 🤖 Upgraded AI Intelligence Reports
- **Structured AI Reports**: Enhanced both Pre-Race (`predicted_report_round_N.md`) and Post-Race (`report_round_N.md`) AI analysis documents across all season rounds (Australia to Dutch GP).
- **High-Impact Architecture**: Includes Executive Summaries (blockquote), Top 10 Race Classification & Pace Hierarchy tables, Victory & Podium Contender breakdowns, 1-Stop Pit Window Strategy (Medium → Hard), and Race Day Watch Points.
- **First-Reading Clarity**: Structured for immediate comprehension by casual fans and technical engineers alike.

#### 📈 Clean Race Timeline Visualization
- **Zero Driver Duplication**: Aggregated lap-level CSV predictions into single per-driver pace entries before constructing `predicted_lap_positions` JSON files, eliminating duplicate driver labels in the interactive chart legend.
- **Unique Driver Grid**: Ensures clean 1-to-1 mapping for every driver on the grid across all season rounds.

#### 🗓️ Future Race Date-Gating & Calendar Alignment
- **Strict Date Gating**: Updated `getAvailableRaces()` in `fileReader.ts` to compare race ISO dates against current time. Future rounds (such as Round 14 Spanish GP on September 13) remain locked until their scheduled weekend arrives.
- **Race Day Continuity**: Fixed date comparison logic in `index.tsx` so race day (Dutch GP on August 23) remains active as the current race throughout the entire race day.
- **Alias Resolution**: Handled `Barcelona_Grand_Prix` / `Spanish_Grand_Prix` directory naming seamlessly.

#### 🔓 Build Artifact Tracking (`.gitignore` Fix)
- **`.gitignore` Exception**: Added targeted exceptions `!reports/**/summaries/*.json` and `!reports/**/summaries/*.md` to ensure all generated race intelligence artifacts are tracked in git and deployed to Vercel.

---

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
