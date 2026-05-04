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
Gemini-powered automated reporting based on ML race residuals.
![AI Race Analysis](images/dashboard/04_ai_analysis.png)

---

## 🌟 Key Features

- **Interactive AI Dashboard**: A modern, dark-mode web interface built with **Next.js 15** and **Tailwind CSS**, providing real-time comparison between AI Predictions and Actual Race Telemetry.
- **Race Tyre Intelligence**: Deep-dive strategy analysis for all 22 drivers, featuring interactive stint timelines and "Business Question" logic.
- **Automated MLOps Pipeline**: Orchestrated via **GitHub Actions** and `master_pipeline.py`. Automated data ingestion from FastF1, model execution, and artifact deployment.
- **Virtual Race Simulation**: Simulates lap-by-lap position changes based on predicted race pace, visualizing the "Predicted vs Actual" delta.
- **Track-Aware Modeling**: Integrates circuit-specific metadata (Downforce, Abrasiveness, Speed Profiles).

---

## 🏗️ Platform Architecture

```text
├── .github/workflows/       # CI/CD Automation (GitHub Actions)
├── dashboard/               # Next.js 15 Web Application
├── scripts/                 # Master Pipeline & Generation Scripts
├── reports/                 # Hierarchical Data Store (Versioned JSON/CSV)
│   └── 2026/
│       ├── summaries/       # Dashboard-ready JSON Artifacts (Round-based)
│       └── {Grand_Prix}/    # Deep-dive ML Reports & Raw Predictions
```

---

## 🚀 Execution Workflow

### 1. Local Development
```bash
uv sync
cd dashboard && npm run dev
```

### 2. Update Race Data
To ingest data for a new Grand Prix (e.g., Canada, Round 5):
```bash
# Via GitHub Actions (Recommended)
# Go to GitHub Actions -> "Update F1 2026 Data" -> Run Workflow
```

---

## 🛠️ Technical Stack

- **ML**: `XGBoost`, `LightGBM`, `Scikit-Learn`, `SHAP`
- **Frontend**: `Next.js 15 (Pages)`, `TypeScript`, `Tailwind CSS`, `Recharts`, `Lucide React`
- **Automation**: `GitHub Actions`, `Docker`, `uv`
- **Data Source**: `FastF1 API`, `OpenF1`

---

**Author**: Juan Jose Restrepo Rosero  
**Philosophy**: "Data is just noise without strategy." This platform focuses on converting complex ML residuals into actionable racing intelligence.
