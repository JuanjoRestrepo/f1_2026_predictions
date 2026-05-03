# 🗺️ F1 Prediction Roadmap: Towards "Full Reliability"

This document outlines the strategic technical evolution of the F1 2026 Predictive Pipeline, addressing current limitations in data volume, track context, and aleatory uncertainty.

---

## 🏎️ Phase 1: Contextual Intelligence (Track Features)
The model currently treats every "EventName" as a categorical label. We will move to a **Feature-Based Track Model**.

### 1.1 Track Characteristics Database
We are introducing `data/external/track_metadata.csv` with the following features:
- **Type**: Street, Permanent, Hybrid.
- **Downforce Level**: Low, Medium, High, Ultra-High.
- **Abrasiveness**: 1-5 scale (affects tyre degradation).
- **Full Throttle %**: Engine power dependency.
- **Corner Profile**: Ratio of Low/Medium/High-speed corners.

### 1.2 Integration Logic
The `simulate_race.py` script will perform a `LEFT JOIN` on `EventName` to inject these features into the training matrix, allowing the model to generalize across similar track profiles even if it hasn't seen a specific track recently.

---

## 📊 Phase 2: Statistical Rigor & Uncertainty
Addressing the "Single Number" prediction fallacy.

### 2.1 Quantile Regression (Aleatory Uncertainty)
Instead of predicting the mean lap time, we will train the `LightGBM` model using the `quantile` objective:
- **Alpha 0.05**: Optimistic pace (Qualifying/Fastest Lap potential).
- **Alpha 0.50**: Median race pace (Current output).
- **Alpha 0.95**: Pessimistic pace (Traffic/Degradation/Mistakes).

### 2.2 Temporal Decay (Form Weighting)
Implementation of a `sample_weight` strategy where:
$$W_i = e^{-\lambda (T_{current} - T_{race})}$$
This ensures that a win in Round 4 has more influence on the Round 5 prediction than a DNF in Round 1.

---

## 🛠️ Phase 3: Model Observability (DevOps Layer)
Closing the feedback loop.

### 3.1 Post-Race Residual Analysis
A new script `scripts/analyze_residuals.py` will run after each GP:
1. Load `standings.csv` (Predicted).
2. Fetch real `FastF1` results (Actual).
3. Calculate **Bias per Team**: Are we systematically overestimating Audi?
4. **Error Distribution**: Are we failing more on Street circuits?

### 3.2 Automated Re-training Trigger
If the **MAPE (Mean Absolute Percentage Error)** exceeds 1.5%, the pipeline will trigger a high-priority re-tuning of hyperparameters.

---

## 📈 Phase 4: Data Augmentation
Addressing the "Small Sample" problem.

- **Cross-Era Normalization**: Use 2024-2025 data but "normalize" it to 2026 performance levels using a scaling factor based on the first 3 rounds. This gives us thousands of additional training rows without the "old car" bias.
- **Simulated Pits**: Integrate pit stop loss and tyre delta (S/M/H) as dynamic variables in the simulation.
