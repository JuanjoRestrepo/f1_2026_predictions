# ADR-002 — Season Rollover and Feature Enrichment

| Field | Value |
|---|---|
| Status | **Proposed** — documentation only; authorizes no implementation, schedule, model, or serving change |
| Date | 2026-11-02 |
| Supersedes | — |
| Related | [PLAN_CLOUD_NATIVE_SERVING.md](PLAN_CLOUD_NATIVE_SERVING.md) (ADR-001), [RUNBOOK_RACE_WEEKEND.md](RUNBOOK_RACE_WEEKEND.md) §4.9, [ARCHITECTURE.md](ARCHITECTURE.md) |
| Scope | Feature engineering roadmap and the cross-season prior model |

> **Read this first.** This ADR records an analysis and a proposed order of work. Nothing here is implemented. Every item needs its own approval, and any new model feature must satisfy the serving-parity rule in §7 before it is trained on.

---

## 1. Context

The project predicts race pace from FastF1 data with two separate contracts:

- **Local (product) model:** a 70-feature pipeline built from `src/f1_predictions/features/`. This is the published model and must be preserved until a validated replacement exists.
- **Cloud (Databricks) contract:** `lap_features_gold` with 13 features (`LAP_FEATURES` in `src/f1_predictions/features/contract.py`), versioned by `FEATURE_CONTRACT_VERSION = 1`.

The cloud table and the local frame are **not interchangeable**. Cloud-native serving is blocked on that mismatch (ADR-001, G1/G3). Any proposal that adds features has to answer three questions:

1. Is the data observable from public sources?
2. Can the serving path compute it at inference time?
3. Does it improve a **time-based** validation split, not just an in-sample fit?

Constraints that shape every decision below:

- Databricks Free Edition: serverless only, one `2X-Small` SQL warehouse, restricted egress, storage and compute quotas.
- Delta/Unity Catalog is the source of truth; Supabase holds the public dashboard bundle only.
- Do not ship a feature the serving path cannot supply.
- Do not fabricate accuracy, laps, or ingestion results.

---

## 2. What the repository already has

Most of the valuable ideas in the external proposal are **already implemented locally**. The gap is parity and documentation, not missing concepts.

| Module | What it does | Notes |
|---|---|---|
| `features/traffic_exposure.py` | Labels laps by gap to the car ahead and measures the dirty-air penalty | Measured on this repository's own laps: +0.57 s under 0.5 s, +0.29 s at 0.5–1.0 s, +0.09 s at 1.0–1.5 s, ~0 s beyond 1.5 s, holding tyre age constant within the stint |
| `features/track_evolution.py` | Rolling median of the field's pace to isolate rubbering-in from driver pace | Currently a rolling statistic, not a state-space filter |
| `features/clean_air_pace.py` | Extracts clean-air long-run pace, filters traffic and lockups, applies Bayesian prior shrinkage on new/semi-street circuits | Compound- and fuel-adjusted reporting; no explicit fuel feature |
| `features/tyre_degradation.py` | OLS slope of `LapTime_s ~ TyreLife` per `(Driver, Stint)` | Linear; no cliff model |
| `features/era_normalization.py` | Adjusts historical lap times for the 2026 regulation change | Guards against predicting physically impossible pace |
| `features/reliability.py` | Brake-wear and PU-strain proxies from sector variance | Proxy only |
| `features/weather.py` | `AirTemp`, `TrackTemp`, `Humidity`, `Rainfall`, `WindSpeed` | Present locally, absent from the cloud contract |
| `features/historical_performance.py` | Cumulative championship points and EWMA form priors computed before the session (leak-free) | Basis for the rollover work in §5 |

Consequence: the roadmap below is mostly **promotion and hardening**, not greenfield modelling.

---

## 3. Feasibility of the external proposal

The proposal mixes three very different data tiers. Treating them as one list is the main risk.

### 3.1 Public data (FastF1, Jolpica/Ergast, OpenF1)

FastF1 exposes lap and sector times, compound and tyre age, stint, position, weather per minute, race-control messages, and car telemetry at roughly 10–25 Hz for a limited channel set (`Speed`, `RPM`, `nGear`, `Throttle`, `Brake`, `DRS`, `X`, `Y`, `Z`, `Distance`).

### 3.2 Team-only data

Ride height, aero balance, pitot pressure, battery state of charge and deployment maps, tyre carcass/core temperature (3-band IR), brake migration, and steering angle are not published. They are not “hard to get”; they are **not observable** from outside the team.

### 3.3 Assessment

| Proposed idea | Observable? | State in repo | Verdict |
|---|---|---|---|
| Slip angle / slip ratio (Pacejka magic formula) | No — needs steering angle and body-frame velocities | Absent | **Reject.** Any proxy would be fabricated physics |
| Ride height, aero balance, real downforce | No — team lasers and load cells | Absent | **Reject** |
| Pitot pressure, aerodynamic yaw | No — team sensors | Absent | **Reject** |
| State of charge, deployment, harvesting | No — PU control data | Absent | **Reject** |
| Tyre carcass temperature (3-band IR) | No — team IR rigs | Absent | **Reject.** Surface behaviour is only inferable from compound, age and pace |
| Brake migration | No — brake-by-wire internals | Proxy in `reliability.py` | **Reject** as a feature; keep the proxy |
| Fuel mass correction | Yes — race distance and lap count | Mentioned, not a feature | **Adopt, P0** (§6) |
| Track evolution index (Kalman) | Yes | Rolling median | **Upgrade, P2** |
| Dirty-air / wake penalty | Yes | Implemented | **Promote to cloud contract, P1** |
| Tyre cliff (XGBoost/LightGBM) | Yes | Linear slope only | **Extend, P2** |
| Monte Carlo SC/VSC pit window | Yes — race-control messages | Absent | **Adopt as offline strategy tool, P1**; not a serving feature |
| Weather features | Yes | Implemented locally | **Promote to cloud contract, P1** |
| Micro-sectors (S1/S2/S3) | Yes | Partial | **Adopt, P2** |
| Per-lap telemetry aggregates (full-throttle %, braking time, DRS) | Yes | Absent | **Evaluate, P2** — measure Volume cost first |
| Ergast/Jolpica history, grid, reliability | Yes | Partial | **Extend, P2** |
| Kaggle datasets | Mixed licensing and provenance | Absent | **Avoid** unless a specific dataset is vetted |
| AWS F1 Insights | Public whitepapers only, no API | Absent | **Read-only reference**; no data |

**Rule:** a rejected item is not “backlog”; it is out of scope until the data source changes.

---

## 4. Corrections to the source material

Recorded so the reasoning is auditable:

- “300 sensors and ~1.1 M points per second” describes a team car, not public data. Public telemetry is a handful of channels at 10–25 Hz for one car at a time. Features must be built from lap, sector, weather and race-control aggregates, not sensor-level physics.
- “Battery stores 4 MJ per lap” is a regulation-level approximation, not a measurement available to us.
- Fuel burn of 1.5–2.0 kg/lap and 0.03–0.04 s/kg are reasonable starting assumptions but must be **calibrated on this dataset**, not taken as constants.

---

## 5. Season rollover: reusing past seasons without contaminating the current one

Seasons are separate regimes. The goal is to start a new season with an informative prior and let the current season take over as evidence accumulates, without ever mixing rows as if they were interchangeable.

### 5.1 Decompose effects, not seasons

```text
lap_time ≈ circuit + car(team, era) + driver + tyre + traffic + weather
```

- **Driver** and **circuit** effects transfer across seasons with reasonably high correlation.
- **Car** performance does not transfer across a regulation change. 2026 introduces lighter cars, a 50/50 ICE/electric split and active aerodynamics; `era_normalization.py` already corrects for that regime break.
- The model carries an explicit **era/regime** identifier so no estimator can silently pool 2025 and 2026 car pace.

### 5.2 Prior construction and blending

For season `S` with `n` completed races:

```text
w(n) = n / (n + k)                 # k ≈ 4–6 races
estimate_S = w(n) · current_S + (1 − w(n)) · prior_S
prior_S   = Σ_seasons λ(Δ) · estimate_past_season   (λ decays with distance and regime change)
```

- Races 1–3: the prior dominates. Races 5–6 onward: the current season dominates.
- `k` is a hyperparameter selected on a **time-based** validation split, never on the test season.
- A regulation change multiplies the cross-regime weight down (for 2027, 2026 is the strongest prior; 2025 and earlier enter mainly through driver and circuit effects).

### 5.3 Within-season recency

Form is not stationary: upgrades, track-specific packages and tyre behaviour drift. Apply exponential decay with a half-life of roughly 3–4 races inside the season, and keep the season-level prior separate from the race-level recency weight.

### 5.4 Circuit priors

Circuit characteristics (downforce level, overtaking difficulty, pit loss, safety-car base rate, degradation severity) are more stable across seasons than car pace. Build a per-circuit prior from all available seasons and let the current weekend update it.

### 5.5 Validation protocol

- **Temporal splits only.** Train on seasons `≤ S−1`, validate on the first 3–5 races of `S`. Never a random row split: laps within a race share tyres, weather and track state.
- Report error **by regime** and by third of the season; a prior that helps early races but hurts mid-season is not a win.
- Compare three baselines: current-season-only, prior-only, and blended. Adopt the blend only if it beats current-season-only in R1–R3 without degrading later races.
- Keep the existing group-CV convention (`Season`, `RoundNumber`) for within-season evaluation.

### 5.6 Failure modes to guard

- **Leakage through normalization.** Era-adjusted historical times must not use statistics from the validation season.
- **Prior collapse.** If `k` is too large, the model ignores the current season; too small and the prior is decorative.
- **Regime drift inside a season** (e.g., a mid-season tyre construction change) — treat it as a regime event, not as noise.

---

## 6. Feature roadmap

Ordered by value per unit of risk. Each item lists its acceptance criterion.

### P0 — Fuel mass correction (highest value, lowest cost)

- Add `fuel_kg` and `lap_time_fuel_corrected_s` derived from race distance and laps completed.
- Calibrate the seconds-per-kg coefficient on this dataset; do not hard-code 0.035.
- Acceptance: corrected pace improves the time-based validation error versus the uncorrected target, and the fitted degradation slope stops being biased negative.
- Serving: both values are computable from lap number and race distance, so the cloud path can supply them.

### P1 — Promote existing local features to the cloud contract

- Weather (`AirTemp`, `TrackTemp`, `Humidity`, `Rainfall`, `WindSpeed`) and traffic exposure are already computed locally.
- Acceptance: `lap_features_gold` carries them under a bumped `FEATURE_CONTRACT_VERSION`, and the DLT build reproduces the local values on a shared fixture.
- This is a prerequisite for any serving cutover; it is not optional polish.

### P1 — Safety-car / VSC strategy tool (offline)

- Derive per-circuit, per-lap SC/VSC base rates from race-control messages.
- Run pit-window Monte Carlo offline; publish the resulting window as an artifact, not as a model feature.
- Acceptance: reproducible simulation seed, documented assumptions, and no serving dependency.

### P2 — Tyre cliff model

- Replace the linear slope with a piecewise or gradient-boosted model of the non-linear drop-off, using tyre age, compound, track temperature and stint laps.
- Acceptance: better stint-end prediction on held-out events; no leakage of future laps.

### P2 — Track evolution as a state-space filter

- Upgrade the rolling median to a Kalman/state-space estimate that separates environmental grip from driver pace.
- Acceptance: lower variance of the evolution estimate on synthetic data with known drift.

### P2 — Sector and telemetry aggregates

- Add S1/S2/S3 and, if storage allows, per-lap telemetry aggregates.
- Acceptance: measured Volume growth and query cost are documented **before** enabling it in production.

### P2 — Historical priors from Jolpica/Ergast

- Grid position, reliability and historical circuit results to feed §5.
- Acceptance: prior-only baseline beats a naive constant on early-season races.

---

## 7. Serving-parity rule

A feature may enter `LAP_FEATURES` only if **all** of the following hold:

1. It is computable at inference time from data the serving path has (no post-race-only fields).
2. It exists in both the local pipeline and the cloud contract, or the local model is explicitly versioned to drop it.
3. Its definition is covered by a test that fails when local and cloud values diverge.
4. The contract version is bumped, and training refuses mismatched versions (already enforced).

Research-only features live outside `LAP_FEATURES` and cannot be trained into the published model.

---

## 8. Implementation plan

No work starts without explicit approval per phase.

| Phase | Work | Gate |
|---|---|---|
| R0 | This ADR reviewed and accepted | Written approval |
| R1 | Fuel correction: data contract, calibration, tests | Time-based validation improvement; no serving change yet |
| R2 | Cloud contract v2: weather + traffic parity | DLT/local parity test green; `FEATURE_CONTRACT_VERSION` bumped |
| R3 | Season rollover: prior model and blending weights | Beats current-season-only in R1–R3 of a held-out season |
| R4 | Offline strategy tooling (SC/VSC Monte Carlo) | Reproducible artifacts; no serving dependency |
| R5 | Optional P2 items, one at a time | Each with its own cost/benefit note |

Sequencing rationale: fuel correction first because it fixes a known bias in the target; parity second because it unblocks serving; rollover third because it needs a stable feature set to compare against.

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Feature creep into a frozen model | Published numbers drift without validation | Serving-parity rule; explicit approval per phase |
| Prior leakage across seasons | Optimistic validation | Temporal splits, era identifiers, no cross-season statistics in normalization |
| Free Edition storage/compute limits | Pipeline failures mid-season | Measure Volume cost before enabling telemetry aggregates |
| Proxy features presented as physics | Misleading analysis | §3 rejects unobservable quantities outright |
| Rollover model overfits one season | Worse early-season predictions | Compare against prior-only and current-season-only baselines |

---

## 10. Revisit triggers

- A public data source begins publishing a previously team-only channel.
- A regulation change alters the regime weighting.
- The cloud contract and local pipeline converge, removing the parity constraint.
- Validation shows the rollover prior does not help early-season races.

---

## 11. References

- [PLAN_CLOUD_NATIVE_SERVING.md](PLAN_CLOUD_NATIVE_SERVING.md) — ADR-001, gaps G1–G12, Phase 22.
- [RUNBOOK_RACE_WEEKEND.md](RUNBOOK_RACE_WEEKEND.md) — §4.9 race-day stub recovery, §4.2 same-day detection.
- [ARCHITECTURE.md](ARCHITECTURE.md) — feature pipeline structure.
- `src/f1_predictions/features/contract.py` — `LAP_FEATURES`, `FEATURE_CONTRACT_VERSION`.
- `src/f1_predictions/features/` — existing feature modules listed in §2.
