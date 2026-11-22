# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v6.8.1] - 2026-11-21

### Fixed
- **Dashboard Hero Card CTA**: Resolved bug where clicking "View AI Intelligence Report" in the Next Grand Prix card (Las Vegas GP) redirected to the previous race (São Paulo GP). The button and status line now dynamically link to `nextRace` whenever pre-race intelligence and predictions are available (`isNextRaceAvailable`), with clear fallback to `latestAvailableRace`.

### Added
- **Round 21 (Las Vegas Grand Prix) Pre-Race Intelligence**:
  - Full virtual race simulation executed with Quantile Regression (P05/P50/P95) and LightGBM pace models.
  - Pre-race weather fetched via Open-Meteo for Las Vegas (AirTemp 9.4°C, TrackTemp 21.4°C, 0% rain).
  - Generated `predictions.csv`, `standings.csv`, `predicted_report_round_21.md`, `predicted_lap_positions_round_21.json`, `predicted_tyre_intelligence_round_21.json`, and `weather_intelligence_round_21.json`.
  - Synced all 10 artifacts to Supabase S3 bucket (`f1-cache/dashboard/2026/`) and triggered production rebuild on Vercel (26 static pages generated).

---

## [v6.8.0] - 2026-11-21

### Added

#### Track Segmentation Engine (`src/f1_predictions/features/track_segmentation.py`)
Implements the methodology from [@formulasteele](https://github.com/j5t3313/f1-strategy-sim) (Jemima Steele — [f1strategysim.com](https://www.f1strategysim.com/)):

- **`TrackCenterline`**: Builds a GPS-based reference centerline `C(s)` from X/Y position data.
  Orthogonal projection using line-segment closest-point formula (`u = clamp(dot/|v|², 0, 1)`)
  for sub-millimetre accuracy vs nearest-vertex approaches.
- **`find_braking_points()`**: Detects physical segment boundaries from telemetry `Brake` + `Speed`
  channels, mirroring the boundary-detection approach in f1-strategy-sim.
- **`validate_lap_quality()`**: Three Steele quality gates before a lap enters analysis:
  - Distance error < 1 % (GPS arc vs integrated speed)
  - Median deviation from centerline < 20 m
  - Segment reconstitution error < 15 ms vs transponder lap time
- **`compute_segment_times()`**: Interpolates elapsed time per physical micro-sector using
  `Distance` and `Time_s` telemetry channels, enabling localized grip/rain detection
  (e.g., T1→T4 impact visible 2 laps before full-lap signal — as demonstrated in the
  2026 São Paulo GP rain analysis).

#### Bayesian Quadratic Tyre Model (`src/f1_predictions/features/bayesian_tyre_model.py`)

- **`TyreParameters`** dataclass: `alpha` (base pace), `beta` (linear deg), `gamma` (quadratic
  deg), `sigma` (lap noise), `rho` (AR(1) autocorrelation), `max_life`.
- **`COMPOUND_PRIORS`**: Calibrated priors for 2026 Pirelli compounds C1–C5.
- **`remove_fuel_effect()`**: Strips 2026 regulation fuel mass penalty
  (92.5 kg start, 0.03 s/kg/lap correction per lap).
- **`fit_quadratic_degradation()`**: OLS polyfit degree-2 regression on cleaned stint data.
- **`solve_closed_form_stint_cost()`**: Analytical closed-form `E[T]` pit-window optimizer —
  no Monte Carlo loop needed; exact for the quadratic degradation family.
- **`generate_ar1_noise()`**: Autocorrelated lap-to-lap pace variance
  `ε_t = ρε_{t-1} + σ√(1-ρ²)·N(0,1)` for realistic tyre simulation.

#### Race Reports — R19 & R20 Full Pipeline Runs

- **Round 19 — Mexico City Grand Prix**: complete ingestion → simulation → `master_pipeline`
  → report cycle. 11 artifacts generated under `reports/2026/Mexico_City_Grand_Prix/results/`.
- **Round 20 — São Paulo Grand Prix**: FastF1 F1TV auth required (2026 season telemetry now
  gated); 71 laps, 22 drivers ingested. 12 artifacts under `reports/2026/Sao_Paulo_Grand_Prix/results/`.
- Summary snapshots for both rounds in `reports/2026/summaries/` (18 JSON/MD files).
- **332 artifacts** published to Supabase S3 `f1-cache/dashboard/2026/`; Vercel rebuild
  triggered (Job `FR4RUJIVDeBhOW28ywPe`); 25 static pages generated (R01–R20).

#### Dashboard — pnpm Migration (Security Hardening)

- Migrated dashboard package management from `npm` to **`pnpm` v10.5.2** via `corepack enable pnpm`.
- Added `pnpm-lock.yaml` at repo root.
- Mitigation for the [TanStack npm supply-chain compromise](https://tanstack.com/blog/npm-supply-chain-compromise-postmortem);
  `npm` is now banned for all dashboard operations per project security policy.

#### Tests

- `tests/unit/test_track_segmentation.py` — 5 unit tests, 92 % line coverage
- `tests/unit/test_bayesian_tyre_model.py` — 4 unit tests, 91 % line coverage
- Combined module coverage: **91.57 %** (threshold: ≥ 80 %)

### Changed

- **`.gitignore`**: Added `f1-strategy-sim-main/` (external reference repo, not part of codebase)
  and Node/workspace artifact entries.
- **`.env.example`**: Documented `F1_USERNAME` and `F1_PASSWORD` variables required for
  FastF1 F1TV authentication (mandatory for 2026+ season telemetry download).

### Fixed

- **`fix(features)`** (merged from `fix/traffic-exposure-compact-positions`):
  Keep traffic exposure position arrays in-bounds after compact filtering;
  prevents `IndexError` when a filtered lap has fewer than 3 position samples.
- **R20 event name shell encoding**: Previous pipeline run corrupted the event name to
  `"SM-CM-#o Paulo"` due to shell UTF-8 expansion. Corrected to `"São Paulo Grand Prix"` →
  `event_slug()` now generates `Sao_Paulo_Grand_Prix/` correctly.
- **`TrackCenterline` projection**: Switched from nearest-vertex (O(N) point search, ~5 m error
  at midpoints) to nearest line-segment projection for sub-mm accuracy.
- **`.env`**: Removed duplicate `F1_USERNAME`/`F1_PASSWORD` credential block introduced during
  manual edit; consolidated to single entry.

### Code Quality

| Check | Result |
|---|---|
| `ruff check` | ✅ All checks passed (13 auto-fixed + D107, E501, I001, F401 manually resolved) |
| `ruff format --check` | ✅ All files formatted |
| `mypy --strict` | ✅ No issues found in 4 source files |
| `pytest` new modules | ✅ 9 passed, 91.57 % coverage |
| `pytest` Databricks suite | ✅ 48 passed, 1 skipped |
| `pnpm build` (dashboard) | ✅ 25 static pages, clean |

---

## [v6.7.0] - 2026-11-14

> See git log for prior release notes. CHANGELOG.md introduced in v6.8.0 retroactively.

---

## [v6.6.1] - 2026-11-10

> Patch release. See git log.

---

## [v6.6.0] - 2026-11-07

> See git log.

---

<!-- older releases available via `git tag --sort=-version:refname` -->
