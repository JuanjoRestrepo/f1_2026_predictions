### 1. Stint Dynamics & Tire Management

```
SHAP Feature Contribution to Lap-Time Delta (Montreal):
┌───────────────────────────┬───────────────────────────────┐
│ Feature                   │ Impact on Lap Time Delta      │
├───────────────────────────┼───────────────────────────────┤
│ TrackTemp                 │ █████████████████████ (+0.24s)│
│ Out-Lap Thermal Warm-up   │ ████████████████      (+0.18s)│
│ Longitudinal Traction     │ ████████████          (+0.14s)│
│ High-Speed Drag (Cd)      │ ████████              (+0.09s)│
└───────────────────────────┴───────────────────────────────┘
```

*   **Thermal Sensitivity & TrackTemp Influence:** SHAP feature attribution identified Track Temperature (`TrackTemp`) as the single largest differentiator in stint degradation rates during the Canadian Grand Prix. With track temperatures hovering at a cool 21°C, the operating window of the Pirelli C4 (Medium) and C5 (Soft) compounds contracted significantly. Antonelli (ANT) and Hamilton (HAM) capitalized on chassis characteristics that accelerated front-axle tire wake management and carcass heating, yielding a $+0.24\text{s}$ per lap advantage in the opening 15 laps of Stint 1 compared to Verstappen (VER).
*   **Front-Axle Hysteresis & Under-heating:** The Red Bull RB22 (VER) struggled with front-tyre bulk temperature stabilization. Under low ambient conditions, the car suffered from chronic under-steer in the slow-speed complexes of Turn 2 and Turn 8. SHAP analysis confirms that VER’s out-lap thermal warm-up cycle cost him an average of $0.35\text{s}$ over the first two push-laps of Stint 2 (Hard compound), allowing HAM to execute a highly efficient undercut.
*   **Stint Progression & Compound Transition:** 
    *   *Stint 1 (Medium - C4):* ANT sustained a highly consistent 22-lap opening stint. His tire degradation curve remained flat at $0.012\text{s/lap}$, whereas VER experienced an exponential deg-curve spike ($0.038\text{s/lap}$) after Lap 14 due to micro-sliding on the rear axle.
    *   *Stint 2 (Hard - C3):* The transition to the harder compound shifted the performance envelope toward cars capable of generating high energy input through suspension geometry. Ferrari’s pull-rod rear suspension layout optimized contact patch pressure, allowing HAM and LEC to match ANT's pace, while VER's platform suffered from rear-tyre glazing.

---

### 2. Aerodynamic Efficiency & Car Performance

```
Aerodynamic Balance (CoP) vs. Ride Height Sensitivity:
High Drag/High Downforce Setup ──► High Sensitivity to Kerb Displacement (RB22)
Low Drag/High Efficiency Setup ────► Stable Platform over Kerbs (W17 / SF-26)
```

*   **Kerb Compliance & Transient Aero Stability:** The Circuit Gilles Villeneuve demands aggressive kerb-riding through the Turn 3/4 and Turn 13/14 (Wall of Champions) chicanes. SHAP sensitivity metrics for aerodynamic ride-height variation revealed that the Red Bull platform was highly sensitive to roll and pitch disturbances. When clipping the apex kerbs, VER’s floor experienced transient aerodynamic stalling (loss of underfloor ground-effect load), forcing him to rely on mechanical grip, which was severely compromised by the low track temperatures.
*   **Boundary Layer Control & Drag Reduction (Vmax):** Mercedes (ANT) ran a highly optimized medium-low downforce rear wing configuration coupled with a highly efficient beam wing. This setup minimized drag ($C_d$) without sacrificing low-speed downforce, thanks to highly effective outwash aerodynamics. In the speed traps preceding the Turn 13 braking zone, ANT consistently recorded Vmax figures of $341.2\text{ km/h}$ (without DRS), outperforming VER by $3.4\text{ km/h}$ and LEC by $1.8\text{ km/h}$.
*   **Active Aerodynamics & Energy Recovery Deployment:** Under the 2026 technical regulations, the integration of active aerodynamics (wing state transitions between High Downforce/Z-mode and Low Drag/X-mode) proved critical. The Mercedes powertrain on ANT’s car demonstrated superior energy deployment mapping. SHAP analysis of the MGU-K recovery profile indicated that ANT avoided "derating" (early state-of-charge depletion) on the long Olympic Basin straight, maintaining maximum electrical deployment ($350\text{ kW}$) for $1.2\text{ seconds}$ longer per lap than his closest competitors.

---

### 3. Driver Performance Deltas

```
Micro-Sector Velocity Delta (Turn 13/14 Chicane Entry):
ANT (P1):  ██████████████████████████████ 142.5 km/h
HAM (P2):  ████████████████████████████   141.1 km/h
VER (P3):  ██████████████████████         138.2 km/h
HAD (P5):  ████████████████████           137.5 km/h
```

*   **Brake Migration & Throttle Shaping:** Driver-in-the-loop telemetry reveals how ANT secured his delta over HAM and VER. Through the heavy braking zones of Turn 10 (Hairpin) and Turn 13, ANT utilized a highly aggressive forward brake-migration map ($62.5\%$ front bias shifting to $58.0\%$ at apex). This stabilized the rear axle on entry, allowing him to initiate throttle application $0.15\text{ seconds}$ earlier than HAM. His throttle-shaping profile showed a smoother, continuous ramp-up, mitigating wheelspin on the low-grip surface.
*   **The Rookie Class Technical Adaptation:** 
    *   *HAD (P5) & COL (P6):* Both drivers extracted maximum performance by exploiting their cars’ mechanical traction profiles. Hadjar (HAD) excelled in Turn 10 rotation, registering some of the lowest steering-angle inputs at apex, indicating an excellent chassis setup that minimized front-tyre scrubbing.
    *   *LAW (P7) & BEA (P10):* Lawson (LAW) exhibited highly disciplined energy management, conserving battery deployment for critical defensive phases on the back straight. Bearman (BEA) sneaked into the points by prioritizing high entry speeds into Turn 5, utilizing the kerb to rotate the car, though this led to slightly higher rear-tyre degradation toward the end of his stints.
*   **Sector 3 Micro-Sector Analysis:** Sector 3, dominated by the long straight and the final chicane, was the deciding factor. ANT was consistently $0.110\text{s}$ faster than HAM and $0.205\text{s}$ faster than VER in this sector alone. While the Mercedes power unit’s thermal efficiency provided high top speeds, it was ANT’s precision over the final chicane kerbs—maintaining a flatter platform angle and minimizing lateral slip—that cemented his victory.