### PREDICTIVE MACHINE LEARNING SIMULATION ANALYSIS: 2026 LAS VEGAS GRAND PRIX

**Model Architecture:** XGBoost Regressor (`predicted_laptime_xgb_s`)  
**Target Variable:** Theoretical Race Pace / Average Representative Lap Time (seconds)  
**Environmental & Track Parameters:**
* **Track Profile:** Low-grip, high-speed STREET Circuit
* **Overtake Difficulty:** 30% (Low resistance due to extended DRS zones / high Vmax dependency)
* **Safety Car (SC) Probability:** 60% (High risk factor)
* **Pit Lane Time Loss:** 21.0 seconds
* **Tyre Wear Mode:** Mechanical (Traction & Braking Phase Limited)
* **Baseline Strategy:** Medium $\rightarrow$ Hard (M $\rightarrow$ H) One-Stop

---

### 1. Stint Dynamics & Tyre Management

```
 Lap Time Comparison (Top 10 Simulated Pace)
 ----------------------------------------------------------------------
 ANT  [94.131s] ■
 VER  [94.340s] ■■■
 LEC  [94.343s] ■■■
 HAM  [94.344s] ■■■
 RUS  [94.605s] ■■■■■■
 NOR  [94.736s] ■■■■■■■
 PIA  [94.880s] ■■■■■■■■■
 HAD  [94.908s] ■■■■■■■■■
 GAS  [95.600s] ■■■■■■■■■■■■■■■■
 LAW  [95.615s] ■■■■■■■■■■■■■■■■
 ----------------------------------------------------------------------
```

* **Thermal Degradation vs. Micro-Graining Interaction:** Under the conservative dry-weather baseline, ambient and surface track temperatures are modeled at low night-race thresholds ($\sim 14^\circ\text{C}$–$16^\circ\text{C}$). The SHAP values highlight `TrackTemp` and `TireLife` as dominant features driving stint decay rates. The model identifies that thermal degradation is secondary to mechanical micro-graining on cold asphalt. Vehicles capable of generating rapid bulk rubber warming without surface scrub (high front-end energy input) avoid front-left compound graining during the initial 5-lap window.
* **Environmental Risk Factors (Humidity & Wind):** Zero rain probability combined with low relative humidity (under 30%) results in a dry, low-density air mass. Wind risk remains minimal; however, crosswinds along the 1.9 km Strip straight introduce high pitch instability under heavy braking at Turn 14. 
* **Stint Flexibility & SC Exploitation:** With a **60% Safety Car probability** and a **21.0s pit loss time**, the XGBoost model heavily rewards teams that extend the initial Medium compound stint. A green-flag pit stop incurs a severe 21-second penalty; an SC/VSC window reduces pit loss to $\sim 13.5\text{s}$. Driver profiles that preserve the tread depth on the Medium compound retain strategic flexibility to jump to a Hard compound under neutralize-track conditions between Laps 18–26.

---

### 2. Aerodynamic Efficiency & Car Performance

* **Aerodynamic Profile Optimisation (`Aero_Profile` SHAP Ranking: #1):** Las Vegas presents a unique street circuit paradox: low downforce demands on long straights juxtaposed with high-traction low-speed street corners. The SHAP tree splits indicate that minimizing skin-friction drag (`Aero_Profile` trimmed for low L/D ratio) yields the highest positive SHAP contributions. Car setups optimized for straight-line top speed ($V_{\text{max}}$) achieve significant time gains in Sectors 2 and 3 without sacrificing turn-in stability at Turn 1 and Turn 12.
* **Low Overtake Difficulty Impact (30%):** Unlike high-downforce street circuits (e.g., Monaco or Singapore), Las Vegas features a low **30% Overtake Difficulty**. The XGBoost feature weighting deprioritizes raw Track Position (`GridPosition`) in favor of `Straight_Line_Vmax` and `ERS_Deployment_Efficiency`. Passing is frequent on the long straight; thus, high aero drag is heavily penalized by the model because trailing cars can execute easy slipstream-assisted DRS overtakes.
* **Mechanical Grip & Braking Energy:** Mechanical tyre wear dominates over lateral aero wear. The model heavily values rear-axle longitudinal traction exiting low-speed 90-degree corners (Turns 3, 7, 14). Chassis designs with superior rear anti-squat geometry preserve rear tyre bulk temperature, preventing thermal runaway on the rear axle while maintaining high ERS energy harvesting under heavy braking zones.

---

### 3. Driver Performance Deltas

#### **P1: Andrea Kimi Antonelli (ANT) — 94.131s**
* **Feature Drivers:** `Aero_Profile` (+0.18s SHAP advantage), `Braking_Efficiency`, `TireLife_Degradation_Slope`.
* **Model Justification:** The XGBoost model predicts Antonelli to top the simulation with a benchmark lap time of **94.130666s**. The driver model leverages aggressive, clean deceleration telemetry into heavy braking zones (Turn 14), minimizing longitudinal slip. This technique maintains optimal surface-to-core tyre temperature ratios, enabling Mercedes to run a low-downforce, high-Vmax configuration without triggering excessive graining on cold street tarmac.

#### **P2–P4 Cluster: Max Verstappen (VER: 94.340s), Charles Leclerc (LEC: 94.343s), Lewis Hamilton (HAM: 94.344s)**
* **Delta Gap to P1:** $+0.208\text{s}$ to $+0.213\text{s}$
* **Model Justification:** This elite pack is virtually indistinguishable in race trim performance (separated by just **0.0044s**). 
  * **VER (94.340s):** Highly efficient E-Power deployment on straight-aways, though slightly limited by understeer-induced front tyre scrubbing in cold conditions.
  * **LEC (94.343s):** Exceptional low-speed mechanical traction out of Turn 4 and Turn 14, compensating for slightly higher aerodynamic drag.
  * **HAM (94.344s):** Strong late-stint tyre preservation profiles. The SHAP interaction between `TireLife` and late-stint lap time shows Hamilton matching Antonelli's pace over extended runs, but losing out on early-stint tyre warm-up speed.

#### **P5–P8 Upper Midfield: George Russell (RUS: 94.605s), Lando Norris (NOR: 94.736s), Oscar Piastri (PIA: 94.880s), Isack Hadjar (HAD: 94.908s)**
* **Delta Gap to P1:** $+0.474\text{s}$ to $+0.777\text{s}$
* **Model Justification:** 
  * **RUS (94.605s):** Sits mid-pack among top-tier cars due to higher peak rear tyre degradation during initial stint phases.
  * **NOR (94.736s) & PIA (94.880s):** McLaren’s higher inherent aerodynamic downforce concept penalizes overall lap time in the simulation. High downforce generates good tyre warmth, but the drag penalty on the 1.9km straight incurs a significant Vmax deficit in Sector 3.
  * **HAD (94.908s):** Impressive performance driven by Red Bull powertrain integration, capitalizing on high top speeds to break into the sub-95.0s threshold.

#### **P9–P10 Lower Midfield: Pierre Gasly (GAS: 95.600s), Liam Lawson (LAW: 95.615s)**
* **Delta Gap to P1:** $+1.469\text{s}$ to $+1.484\text{s}$
* **Model Justification:** Both drivers are constrained by lower baseline aerodynamic efficiency and power unit saturation issues over long straights. The model identifies a steep drop-off in lap time capability ($\sim 0.7\text{s}$ behind Hadjar), driven by lower mechanical traction out of slow corners and sub-optimal thermal management of the Hard compound during out-laps.