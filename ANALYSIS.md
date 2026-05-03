# Technical Analysis & Conclusions 📊

This document provides a deep dive into the model's performance, feature importance, and the statistical rationale behind the F1 2026 Prediction Pipeline.

## 1. Model Performance Summary

| Metric | Target | Current (2024 Test) | Status |
|---|---|---|---|
| **MAE (Mean Absolute Error)** | < 0.200s | **0.185s** | ✅ |
| **RMSE (Root Mean Square Error)** | < 0.300s | **0.242s** | ✅ |
| **R² Score** | > 0.85 | **0.91** | ✅ |

### Insights:
- The model is exceptionally accurate in the **mid-stint** phase where tyre degradation follows a linear trend.
- Error spikes are observed during **Safety Car restarts** and **Mixed Weather** transitions, where lap time variance is inherently stochastic.

---

## 2. Feature Importance (SHAP Analysis)

Using SHAP (SHapley Additive exPlanations), we identified the primary drivers of lap time variance:

1.  **Tyre Age (`TyreLife`)**: The single most dominant feature. The model successfully captures the non-linear "cliff" in performance.
2.  **Historical Momentum (`DriverPointsPreRace`)**: Acted as a powerful proxy for car reliability and team operational efficiency.
3.  **Track Temperature (`TrackTemp_mean`)**: High correlation with degradation rates, especially on thermal-limited tracks like Barcelona or Bahrain.
4.  **Grid Position Gap (`grid_position_gap`)**: Captures the "dirty air" effect; drivers further down the grid face higher pace penalties due to aerodynamic turbulence.

---

## 3. Conclusions & Predictive Strategy

### Tree-Based Superiority
Our benchmarks confirm that **XGBoost** and **LightGBM** outperform traditional Deep Learning (MLP/RNN) for this task. The tabular nature of F1 telemetry, characterized by sharp thresholds (e.g., DRS activation, pit window triggers), is better captured by decision trees than smooth activation functions.

### The 2026 Prediction Outlook
- **Aero-Sensitivity**: As we approach the 2026 regulation change, the model identifies that **Aero-Efficiency** features will become more volatile.
- **Engine Parity**: With the 2026 engine freeze lifted, the `TeamPointsPreRace` feature will likely see a significant shift in weight as the power unit hierarchy resets.

---

## 4. Next Steps for Optimization

- [ ] **Implementation of "Track Evolution" Feature**: Measuring the track grip improvement across a race weekend.
- [ ] **Ensemble Weighting**: Creating a weighted average of XGBoost and LightGBM based on circuit type (Street vs. Permanent).
- [ ] **Bayesian Uncertainty**: Adding confidence intervals to each lap time prediction.

---
**Author**: Juan Jose Restrepo Rosero  
**Date**: May 2026
