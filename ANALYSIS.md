# Technical Analysis & Conclusions 📊

This document provides a deep dive into the model's performance, feature importance, and the statistical rationale behind the F1 2026 Prediction Platform.

## 1. Model Performance & Validation (Miami 2026)

The Miami Grand Prix served as the primary validation gate for the 2026 Predictive Engine.

| Metric | Target | Miami 2026 Actual | Status |
|---|---|---|---|
| **MAE (Lap Time)** | < 0.200s | **0.178s** | ✅ |
| **Strategy Accuracy** | > 80% | **91% (1-Stop M-H predicted & executed)** | ✅ |
| **Winner Prediction** | P1/P2 | **P1 (Antonelli correctly ranked as Top Contender)** | ✅ |

## 2. Model Evolution & Optimization (Canada 2026 Preparation)

Building upon the Miami validation, the predictive engine was optimized for the **Canada Grand Prix**:

| Metric / Feature | Enhancement Implemented | Impact |
|---|---|---|
| **Hyperparameter Tuning** | Transitioned from hardcoded parameters to Bayesian Optimization via **Optuna** (50+ trials). | Improved XGBoost generic MAE from `~0.250s` down to **`0.1978s`**, breaking the target threshold. |
| **Track Evolution Factor** | Added rolling median delta of top lap times to capture "rubbering-in" effects. | Corrects the model's previous underestimation of the Hard compound during the late stages of the race. |
| **Reliability Proxies** | Engineered `Brake_Wear_Proxy` (Sector 3 variance) and `PU_Strain_Index` (Cumulative Distance * TrackTemp). | Accounts for the severe mechanical strain specific to Circuit Gilles Villeneuve (Wall of Champions). |
| **Evaluation Metrics** | Integrated **MAPE** (Mean Absolute Percentage Error) to `RegressionMetrics`. | Provides proportional context to the MAE for varying lap lengths. |

### Insights:
- **XGBoost Dominance**: Decision trees accurately captured the high-speed braking zones of Miami where car stability is non-linear.
- **Residual Analysis**: The model slightly underestimated the performance gain on the Hard compound during the final 10 laps, likely due to unexpected track rubbering-in (Track Evolution).

![Residual Analysis](reports/2026/Miami_Grand_Prix/analysis_visuals/modeling/fig_07_residuals.png)
> [Interactive Report: Predicted vs Actual](reports/2026/Miami_Grand_Prix/analysis_visuals/modeling/fig_05_predicted_vs_actual.html)

---

---

## 3. Feature Importance (SHAP Analysis)

Our SHAP values identify the primary drivers of the 2026 performance hierarchy:

1.  **Tyre Thermal Stability (`TrackTemp_vs_Compound`)**: Crucial in Miami (>50°C track). The model correctly predicted the "thermal cliff" for the Soft compound.
2.  **Aero-Efficiency (`2026_Aero_Profile`)**: Captures the reduced downforce of the new regulations, correctly penalizing teams with high drag in the long straights.
3.  **Historical Form (`WeightedForm_4R`)**: Exponential weighting of the last 4 rounds proved superior to season-averages for capturing Mercedes' recent development surge.

![SHAP Summary](reports/2026/Miami_Grand_Prix/analysis_visuals/modeling/fig_07_shap_summary.png)
![SHAP Bar](reports/2026/Miami_Grand_Prix/analysis_visuals/modeling/fig_08_shap_bar.png)
> [Interactive Report: Feature Importance Explorer](reports/2026/Miami_Grand_Prix/analysis_visuals/modeling/fig_06_feature_importance.html)

---

---

## 4. Exploratory Data Analysis (EDA)

Before modeling, a comprehensive EDA was performed to validate the data distribution and feature correlations for the Miami circuit.

| Distribution | Tyre Degradation |
|---|---|
| ![Laptime Distribution](reports/2026/Miami_Grand_Prix/analysis_visuals/eda/fig_01_laptime_distribution.png) | ![Tyre Degradation](reports/2026/Miami_Grand_Prix/analysis_visuals/eda/fig_02_tyre_degradation.png) |

| Correlation Matrix | Points vs Laptime |
|---|---|
| ![Correlation Matrix](reports/2026/Miami_Grand_Prix/analysis_visuals/eda/fig_03_correlation_matrix.png) | ![Points vs Laptime](reports/2026/Miami_Grand_Prix/analysis_visuals/eda/fig_04_points_vs_laptime.png) |

---

---

## 5. Strategy Intelligence (Tyre Logic)

The "Business Question" engine validated that the **Medium-to-Hard (1-Stop)** strategy was the mathematically optimal solution. 
- **AI Recommendation**: Pit at Lap 24 for optimal traffic window.
- **Actual Winner (ANT)**: Pit at Lap 26.
- **Delta**: 2 laps. The AI-suggested window was within the 95% confidence interval of the actual winning strategy.

---

---

## 6. Platform Conclusions

### High-Fidelity Technical Narratives
The integration of **Gemini 2.5 Flash** now follows a strict "Engineering Persona" protocol. All reports are synthesized with a focus on stint dynamics and aerodynamic efficiency deltas, removing generic analysis in favor of high-level technical debriefs.

### 2026 Outlook
With the successful deployment of the **Optuna Tuner** and **Track Evolution / Reliability** features for Canada (Round 5), the model is now significantly more robust for high-speed, heavy-braking circuits. Future iterations will focus on scaling these reliability heat maps for extreme altitude tracks like Mexico.

---
**Author**: Juan Jose Restrepo Rosero  
**Date**: May 2026

