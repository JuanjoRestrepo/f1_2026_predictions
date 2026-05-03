# F1 2026 Season Predictions Pipeline 🏎️💨

![F1 Prediction Dashboard](images/f1_prediction_dashboard_hero.png)

An automated, elite machine learning pipeline designed to predict Formula 1 race pace and season outcomes. Leveraging historical data from the Ground Effect era (2022-present) with a professional DevOps orchestration layer.

---

## 🌟 Key Features

- **Automated Data Ingestion**: Seamless integration with the `FastF1` API. Supports chunked ingestion to prevent memory overhead.
- **Elite Hierarchical Reporting**: Organizes results by `Year / Grand Prix / Results` for deep-dive race analysis.
- **Dual-Model Architecture**: Benchmarks **XGBoost** and **LightGBM**. Current 2026 MAE: **0.200s** (LightGBM).
- **Professional DevOps**: Orchestrated via `Makefile` and `Docker`, ensuring 100% environment consistency and automatic cleanup.

---

## 🏗️ Hierarchical Structure (Elite Reporting)

The pipeline now organizes all outputs into a versioned, multi-dimensional hierarchy:

```text
reports/
└── {Year}/
    ├── {Grand_Prix_Name}/
    │   └── results/
    │       ├── REPORTE_{Grand_Prix_Name}_{Year}.html  <-- Dynamic GP Report
    │       ├── standings.csv                        <-- Race-specific results
    │       └── miami_race_preview.png               <-- High-fidelity visualizations
    └── REPORTE_GLOBAL_TEMPORADA_{Year}.html          <-- Seasonal Summary
```

---

## 🚀 Execution Workflow (Standard Operating Procedure)

Follow these commands in order to execute the full pipeline using **Docker (Recommended)**.

### 1. Project Setup
```bash
# Build the production image
make build
```

### 2. Data Ingestion
Ingest historical or current season data. Use `--rounds` for specific races if memory is limited.
```bash
# Ingest full 2025 season
make ingest YEAR=2025

# Ingest current 2026 season rounds
make ingest YEAR=2026
```

### 3. Generate Seasonal Predictions
Train on historical data and predict the outcome of the target season.
```bash
# Predict 2026 using 2022-2025 as training
make predict TRAIN_YEARS="2022 2023 2024 2025" PREDICT_YEAR=2026
```

### 4. Technical Reporting
Generate deep-dive HTML reports for the entire season or a specific Grand Prix.
```bash
# Full Season Report
make report TEST_YEAR=2026 TRAIN_YEARS="2022 2023 2024 2025"

# Specific Grand Prix Report (e.g. Japanese GP)
make report TEST_YEAR=2026 EVENT="Japanese Grand Prix" TRAIN_YEARS="2022 2023 2024 2025"
```

### 5. Visualizations (Race Previews)
Generate aesthetic visualizations for upcoming races.
```bash
# Miami GP Race Preview
make miami-viz
```

### 6. Cleanup
Remove orphan containers and temporary execution files.
```bash
make clean
```

---

## 📊 Technical Stack

- **ML**: `scikit-learn`, `xgboost`, `lightgbm`, `shap`
- **Data**: `pandas`, `polars`, `pyarrow`, `fastf1`
- **Quality**: `mypy` (Strict), `ruff`, `pytest` (80%+ coverage)
- **Infra**: `Docker`, `Docker Compose`, `Makefile`, `uv`

---

**Author**: Juan Jose Restrepo Rosero
**Rationale**: Tree-based models consistently outperform deep learning on structured/tabular problems (Grinsztajn et al., 2022). This project prioritizes GBM architectures for maximum predictive accuracy in F1 race dynamics.
