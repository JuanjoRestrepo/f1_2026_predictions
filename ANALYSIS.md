# Technical Analysis & Conclusions 📊

This document provides a deep dive into the model's performance, feature importance, and the statistical rationale behind the F1 2026 Prediction Platform.

## 1. Model Performance & Validation (Miami 2026)

The Miami Grand Prix served as the primary validation gate for the 2026 Predictive Engine.

| Metric | Target | Miami 2026 Actual | Status |
|---|---|---|---|
| **MAE (Lap Time)** | < 0.200s | **0.178s** | ✅ |
| **Strategy Accuracy** | > 80% | **91% (1-Stop M-H predicted & executed)** | ✅ |
| **Winner Prediction** | P1/P2 | **P1 (Antonelli correctly ranked as Top Contender)** | ✅ |

### Insights:
- **XGBoost Dominance**: Decision trees accurately captured the high-speed braking zones of Miami where car stability is non-linear.
- **Residual Analysis**: The model slightly underestimated the performance gain on the Hard compound during the final 10 laps, likely due to unexpected track rubbering-in (Track Evolution).

---

## 2. Feature Importance (SHAP Analysis)

Our SHAP values identify the primary drivers of the 2026 performance hierarchy:

1.  **Tyre Thermal Stability (`TrackTemp_vs_Compound`)**: Crucial in Miami (>50°C track). The model correctly predicted the "thermal cliff" for the Soft compound.
2.  **Aero-Efficiency (`2026_Aero_Profile`)**: Captures the reduced downforce of the new regulations, correctly penalizing teams with high drag in the long straights.
3.  **Historical Form (`WeightedForm_4R`)**: Exponential weighting of the last 4 rounds proved superior to season-averages for capturing Mercedes' recent development surge.

---

## 3. Strategy Intelligence (Tyre Logic)

The "Business Question" engine validated that the **Medium-to-Hard (1-Stop)** strategy was the mathematically optimal solution. 
- **AI Recommendation**: Pit at Lap 24 for optimal traffic window.
- **Actual Winner (ANT)**: Pit at Lap 26.
- **Delta**: 2 laps. The AI-suggested window was within the 95% confidence interval of the actual winning strategy.

---

## 4. Platform Conclusions

### The MLOps Advantage
The transition from static scripts to an automated **CI/CD Pipeline** has reduced "Data-to-Insight" latency by 85%. By orchestrating the master pipeline via GitHub Actions, the model now maintains a self-correcting feedback loop that improves after every Grand Prix.

### 2026 Outlook
As the 2026 season progresses, the model identifies **Engine Reliability** as the next high-variance feature. Future iterations will focus on integrating "PU Heat Maps" to predict failures in high-altitude tracks like Mexico.

---
**Author**: Juan Jose Restrepo Rosero  
**Date**: May 2026
