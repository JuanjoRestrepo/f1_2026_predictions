# F1 2026 Season Predictions Pipeline 🏎️💨

An automated, end-to-end machine learning pipeline designed to predict Formula 1 race pace and season outcomes for 2025 and 2026. Leveraging historical data from the Ground Effect era (2022-present), the system employs Gradient Boosting architectures to model tyre degradation, atmospheric conditions, and driver momentum.

---

## 🌟 Key Features

- **Automated Data Ingestion**: Seamless integration with the `FastF1` API for telemetry, weather, and results.
- **Advanced Feature Engineering**:
  - OLS-based tyre degradation slopes.
  - Rolling pace analysis (Short/Long window volatility).
  - Historical momentum tracking (Pre-race championship points).
  - Weather context broadcasting (Air/Track Temp, Rainfall).
- **Dual-Model Architecture**: Benchmarks both **XGBoost** and **LightGBM** to select the optimal predictor for specific circuit profiles.
- **Professional CI/CD**: Enforces strict `mypy` (type safety), `ruff` (linting), and `pytest` (80%+ coverage) standards.
- **Rich Reporting**: Automated HTML report generation with SHAP explainability and performance metrics (MAE/RMSE).

---

## 🏗️ Architecture (Medallion Structure)

The pipeline follows a robust data engineering architecture to ensure idempotency and reproducibility:

1.  **Bronze Layer (`data/raw/`)**: Raw Parquet files from FastF1. Immutable.
2.  **Silver Layer (`data/processed/`)**: Cleaned and normalized data. Standardized driver/team identifiers and outlier filtering applied.
3.  **Gold Layer (`data/outputs/`)**: Feature-engineered matrices ready for training and inference.

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.12+**
- **uv** (High-performance package manager)

### Installation
```bash
# Clone the repository
git clone https://github.com/JuanjoRestrepo/f1_2026_predictions.git
cd f1_2026_predictions

# Install dependencies and create virtual environment
uv sync
```

### Configuration
Create a `.env` file in the root directory:
```env
F1_CACHE_DIR=./cache/fastf1
F1_DATA_RAW_DIR=./data/raw
F1_DATA_PROCESSED_DIR=./data/processed
F1_DATA_OUTPUTS_DIR=./data/outputs
F1_REPORTS_DIR=./reports
```

---

## 🛠️ Usage

### 1. Generate Performance Reports
Evaluate model health on historical seasons:
```bash
uv run python scripts/generate_reports.py --train-years 2022 2023 --test-year 2024
```

### 2. Predict Future Seasons
Run inference for the 2026 season:
```bash
uv run python scripts/predict_season.py --train-years 2022 2023 2024 2025 --predict-year 2026
```

### 3. Local Quality Checks
Mirror the GitHub Actions CI pipeline:
```bash
# Linting & Formatting
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type Checking
uv run mypy src/ --strict

# Testing with Coverage
uv run pytest --cov=src --cov-fail-under=80
```

---

## 📊 Technical Stack

- **ML**: `scikit-learn`, `xgboost`, `lightgbm`, `shap`
- **Data**: `pandas`, `pyarrow`, `fastf1`
- **Quality**: `mypy` (Strict), `ruff`, `pytest`, `pytest-cov`
- **DevOps**: `GitHub Actions`, `uv`

---

## 📈 Current Project Status
- **Coverage**: ~90% ✅
- **Linting**: Ruff Clean ✅
- **Inference**: Active for 2025/2026 ✅

---
**Author**: Juan Jose Restrepo Rosero
**Rationale**: Per Grinsztajn et al. (2022), tree-based models consistently outperform deep learning on structured/tabular problems. This project prioritizes GBM architectures for maximum predictive accuracy in F1 race dynamics.
