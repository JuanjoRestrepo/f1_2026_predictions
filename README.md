# F1 2026 Season Predictive Platform 🏎️📊🤖

![F1 Prediction Dashboard Header](images/dashboard/01_header_metrics.png)

A production-grade, end-to-end MLOps platform designed to predict Formula 1 race dynamics for the 2026 regulation era. This system combines state-of-the-art Gradient Boosting (XGBoost/LightGBM) with a high-fidelity interactive dashboard inspired by F1 TV telemetry.

---

## 📸 Platform Interface Preview

### 1. Race Timeline & Global Standings
Interactive position chart with real-time "Predicted vs Actual" toggle.
![Race Timeline & Finishing Order](images/dashboard/02_timeline_order.png)

### 2. Tyre Strategy Intelligence
AI-driven stint analysis and business question engine for optimal pit-stop windows.
![Tyre Strategy Intelligence](images/dashboard/03_tyre_intelligence.png)

### 3. AI-Generated Race Narratives
Expert-level race reporting powered by **Gemini 2.0/2.5 Flash**, analyzing telemetry residuals and strategic outcomes with professional engineering personas.
![AI Race Analysis](images/dashboard/04_ai_analysis.png)

---

## 🌟 Key Features

- **F1 Broadcast Aesthetics**: A high-fidelity interface with official team colors and `Solid vs Dashed` line styles to differentiate teammates.
- **Differentiated Analysis**: Unique AI narratives for both **Actual Results** (post-race debrief) and **Predicted ML Simulations** (pre-race forecasting).
- **Mission-Critical Reliability**: Integrated **AI Retry Logic** and professional **Engineering Fallbacks** that maintain a "Strategic Intelligence" persona even during API rate limits.
- **Race Tyre Intelligence**: Deep-dive strategy analysis for all 22 drivers, featuring interactive stint timelines and "Business Question" logic.
- **Automated MLOps Pipeline**: Orchestrated via `scripts/master_pipeline.py`. Automated data ingestion from FastF1, ML model inference, and AI report generation.

---

### 🏗️ Platform Architecture

```text
├── .github/workflows/       # CI/CD Automation (GitHub Actions)
├── dashboard/               # Next.js 15 Web Application
├── scripts/                 # Master Pipeline (Orchestrator) & Training Scripts
├── models/                  # Trained XGBoost/LightGBM Model Artifacts
├── data/                    # Raw Historical Telemetry & Datasets (Bronze Layer)
├── images/                  # Documentation Assets & UI Screenshots
├── reports/                 # Hierarchical Data Store (Medallion Architecture)
│   └── 2026/
│       ├── summaries/       # Dashboard-ready JSON/MD Artifacts (Gold Layer)
│       └── {Grand_Prix}/    # Deep-dive ML Reports & Raw Predictions (Silver Layer)
```

---

## 🚀 Execution Workflow

### 1. Local Development
```bash
uv sync
cd dashboard && npm run dev
```

### 2. Update Race Data
To ingest and analyze any Grand Prix (e.g., Canada Round 5, Spain Round 6):
```bash
# General orchestrator for any GP
uv run scripts/master_pipeline.py --round [ROUND_NUM]
```

---

## 🛠️ Technical Stack

- **ML**: `XGBoost`, `LightGBM`, `Scikit-Learn`, `SHAP`
- **AI**: `google-genai` (Gemini 2.5 Flash)
- **Frontend**: `Next.js 15 (Pages)`, `TypeScript`, `Tailwind CSS`, `Recharts`
- **Automation**: `GitHub Actions`, `uv`
- **Data Source**: `FastF1 API`

---

**Author**: Juan Jose Restrepo Rosero  
**Philosophy**: "Data is just noise without strategy." This platform focuses on converting complex ML residuals into actionable racing intelligence.
