# Project Releases & Versioning 🏁📜

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
