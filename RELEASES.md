# Project Releases & Versioning 🏁📜

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
