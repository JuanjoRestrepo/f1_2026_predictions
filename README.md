# F1 2026 Season Predictions Pipeline 🏎️💨

![F1 Prediction Dashboard](images/f1_prediction_dashboard_hero.png)

An automated, elite machine learning pipeline designed to predict Formula 1 race pace and season outcomes. Leveraging historical data from the Ground Effect era (2022-present) with a professional DevOps orchestration layer.

---

## 🌟 Key Features

- **Automated Data Ingestion**: Seamless integration with the `FastF1` API. Supports chunked ingestion to prevent memory overhead.
- **Virtual Race Simulation**: General-purpose race simulator that predicts performance hierarchies for any GP based on current season form, applying temporal decay (Exponential Weighting) to emphasize recent results.
- **Track-Aware Modeling**: Integrates circuit-specific metadata (Downforce, Abrasiveness, Speed Profiles) to provide context-aware predictions across different track archetypes.
- **Probabilistic Forecasting**: Uses Quantile Regression to output 90% Confidence Intervals (P05/P95) instead of brittle point estimates, visualizing uncertainty.
- **Multi-Era Normalization**: Dynamically penalizes historical lap times (2022-2025) based on aerodynamic profiles to construct a physically accurate "Virtual 2026" training set.
- **Automated Observability**: Closed-loop MLOps architecture (`main.py validate`) that measures Mean Absolute Error (MAE) against real telemetry and auto-triggers model retraining if error thresholds are exceeded.
- **Dual-Model Architecture**: Benchmarks **XGBoost** and **LightGBM**. Current 2026 MAE: **0.185s** (LightGBM).
- **Professional DevOps**: Orchestrated via `main.py` and `uv`, ensuring reproducibility and high performance.

---

## 🏗️ Hierarchical Structure (Elite Reporting)

The pipeline organizes all outputs into a versioned, multi-dimensional hierarchy:

```text
reports/
└── {Year}/
    ├── {Grand_Prix_Name}/
    │   └── results/
    │       ├── standings.csv                        <-- Base prediction data
    │       ├── report_{Year}_{GP}.html              <-- Professional HTML Report
    │       └── visual_ranking_{Year}_{GP}.png       <-- High-fidelity Infographic
    └── predictions/                                 <-- Seasonal aggregate data
```

---

## 🚀 Execution Workflow (Standard Operating Procedure)

The entire pipeline is now orchestrated through a single entry point for maximum efficiency.

### 1. Project Setup
Ensure you have `uv` installed and the environment configured.
```bash
# Sync dependencies
uv sync
```

### 2. End-to-End Race Simulation (Recommended)
The fastest way to simulate a race and generate all visual reports in one go:
```bash
# Run simulation and visualization for Miami GP
uv run main.py --round 4 --event "Miami Grand Prix"
```

### 3. Granular Execution (Modular Steps)
If you need to run specific parts of the pipeline:

#### A. Virtual Race Simulation
Generates the predicted race pace data (CSV).
```bash
uv run scripts/simulate_race.py --year 2026 --round 4 --event "Miami Grand Prix"
```

#### B. Visual Report Generation
Generates the HTML and PNG artifacts from existing CSV data.
```bash
uv run scripts/visualize_results.py --year 2026 --event "Miami Grand Prix"
```

### 4. Observability & Auto-Retraining
Validate predictions against real telemetry and trigger re-training if MAE > 0.300s.
```bash
uv run main.py validate --year 2026 --round 4 --event "Miami Grand Prix"
```

### 5. Technical Seasonal Reporting
Generate deep-dive technical reports for the entire season.
```bash
# Full Season Report
uv run scripts/generate_reports.py --train-years 2022 2023 2024 2025 --test-year 2026
```

## 🗺️ Project Roadmap Status

The predictive engine has evolved from a static script to a full MLOps framework.
- ✅ **Phase 1 (Contextual Intelligence)**: Track characteristic DB injection completed.
- ✅ **Phase 2 (Statistical Rigor)**: Quantile Regression & Temporal Decay implemented.
- ✅ **Phase 3 (Model Observability)**: Automated residual analysis and MLOps feedback loops completed.
- ✅ **Phase 4 (Data Normalization)**: Cross-Era aerodynamic scaling implemented for 2026 physics.

See the detailed [ROADMAP.md](ROADMAP.md) for technical implementation history.

---

## 📊 Technical Stack

- **ML**: `scikit-learn`, `xgboost`, `lightgbm`, `shap`
- **Data**: `pandas`, `polars`, `pyarrow`, `fastf1`
- **Quality**: `mypy` (Strict), `ruff`, `pytest`
- **Infra**: `uv`, `main.py` Orchestrator, `Docker`, `Makefile`

---

**Author**: Juan Jose Restrepo Rosero  
**Rationale**: Tree-based models consistently outperform deep learning on structured/tabular problems (Grinsztajn et al., 2022). This project prioritizes GBM architectures for maximum predictive accuracy in F1 race dynamics.
