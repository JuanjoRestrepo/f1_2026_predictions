"""Bayesian quadratic tyre degradation model and closed-form strategy solver.

Inspired by @formulasteele (f1-strategy-sim):
1. Quadratic Degradation Formulation:
   mu(lap) = alpha + beta * lap + gamma * lap^2
   - alpha: Zero-fuel theoretical baseline pace.
   - beta: Linear wear rate dominating early-to-mid stint.
   - gamma: Quadratic cliff acceleration as rubber depth degrades.

2. 2026 Technical Regulations Fuel Correction:
   - Energy-based fuel flow limit: 3000 MJ/h.
   - Sustainable fuel with lower energy density (38-41 MJ/kg).
   - Starting mass: ~92.5 kg (89.5 kg usable after 3.0 kg reserve).
   - Linear weight penalty: 0.03 s / kg / lap.

3. AR(1) Autocorrelated Lap Variance:
   epsilon_t = rho * epsilon_{t-1} + sigma * sqrt(1 - rho^2) * Normal(0, 1)

4. Closed-Form Pit Window Optimizer:
   Analytically minimizes expected stint summation without simulation:
   E[T] = sum_{stints} [ alpha*L + beta*sum(k) + gamma*sum(k^2) ] + N_stops * pit_loss
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# 2026 Formula 1 technical regulation defaults
DEFAULT_FUEL_START_KG: float = 92.5
DEFAULT_FUEL_RESERVE_KG: float = 3.0
DEFAULT_WEIGHT_EFFECT_S_PER_KG: float = 0.03

# Compound-specific calibrated informative priors for 2026 Pirelli compounds
COMPOUND_PRIORS: dict[str, dict[str, float]] = {
    "SOFT": {
        "alpha": 85.0,
        "beta": 0.070,
        "gamma": 0.0015,
        "sigma": 0.35,
        "rho": 0.40,
        "max_life": 26.0,
    },
    "MEDIUM": {
        "alpha": 85.8,
        "beta": 0.040,
        "gamma": 0.0008,
        "sigma": 0.30,
        "rho": 0.35,
        "max_life": 38.0,
    },
    "HARD": {
        "alpha": 86.4,
        "beta": 0.020,
        "gamma": 0.0004,
        "sigma": 0.28,
        "rho": 0.30,
        "max_life": 52.0,
    },
}


@dataclass(frozen=True)
class TyreParameters:
    """Parameters defining compound degradation and aleatoric noise.

    Attributes:
        compound: 'SOFT', 'MEDIUM', 'HARD', etc.
        alpha: Zero-fuel reference lap time (s).
        beta: Linear degradation rate (s/lap).
        gamma: Quadratic cliff coefficient (s/lap^2).
        sigma: Inherent lap-to-lap pace dispersion (s).
        rho: AR(1) autocorrelation coefficient.
        max_life: Maximum recommended stint length.
    """

    compound: str
    alpha: float
    beta: float
    gamma: float
    sigma: float
    rho: float
    max_life: float

    def expected_lap_time(self, lap_age: int) -> float:
        """Evaluate deterministic degradation at a given tyre age."""
        return self.alpha + self.beta * lap_age + self.gamma * (lap_age**2)


def remove_fuel_effect(
    lap_times_s: NDArray[np.float64],
    current_laps: NDArray[np.int64],
    total_laps: int,
    starting_fuel_kg: float = DEFAULT_FUEL_START_KG,
    reserve_fuel_kg: float = DEFAULT_FUEL_RESERVE_KG,
    weight_effect_s_per_kg: float = DEFAULT_WEIGHT_EFFECT_S_PER_KG,
) -> NDArray[np.float64]:
    """Isolate pure tire degradation by stripping the fuel burn-off benefit.

    As fuel burns, cars gain ~0.03s per kg. If not subtracted, fuel burn
    masks tire degradation, biasing the wear slope downward.

    Args:
        lap_times_s: Array of observed lap times in seconds.
        current_laps: Array of corresponding lap numbers (1-indexed).
        total_laps: Total race distance in laps.
        starting_fuel_kg: Starting fuel mass.
        reserve_fuel_kg: Residual fuel mass at race finish.
        weight_effect_s_per_kg: Lap time sensitivity to fuel mass.

    Returns:
        Array of fuel-corrected zero-fuel lap times.
    """
    usable_fuel = max(0.0, starting_fuel_kg - reserve_fuel_kg)
    fuel_per_lap = usable_fuel / max(1, total_laps)
    # Laps remaining including current
    laps_remaining = total_laps - current_laps + 1
    fuel_mass_on_lap = reserve_fuel_kg + laps_remaining * fuel_per_lap
    fuel_penalty_s = fuel_mass_on_lap * weight_effect_s_per_kg

    return lap_times_s - fuel_penalty_s


def fit_quadratic_degradation(
    lap_ages: NDArray[np.int64],
    zero_fuel_lap_times_s: NDArray[np.float64],
) -> tuple[float, float, float]:
    """Fit the quadratic model: y = alpha + beta * x + gamma * x^2.

    Args:
        lap_ages: Array of tire ages (1, 2, ...).
        zero_fuel_lap_times_s: Array of fuel-corrected lap times.

    Returns:
        Tuple of (alpha, beta, gamma).
    """
    if len(lap_ages) < 3:
        # Fallback to mean and zero degradation
        return float(np.mean(zero_fuel_lap_times_s)), 0.0, 0.0

    # Polynomial fit of degree 2: p(x) = p[0]*x^2 + p[1]*x + p[2]
    poly = np.polyfit(lap_ages, zero_fuel_lap_times_s, deg=2)
    gamma = float(poly[0])
    beta = float(poly[1])
    alpha = float(poly[2])

    # Guard against unphysical negative degradation on small samples
    if beta < 0:
        beta = 0.0
    if gamma < 0:
        gamma = 0.0

    return alpha, beta, gamma


def solve_closed_form_stint_cost(
    params: TyreParameters,
    stint_length: int,
    initial_age: int = 0,
) -> float:
    """Compute the analytical expected elapsed time of a stint without simulation.

    Sum of k for k=1..L is L*(L+1)/2.
    Sum of k^2 for k=1..L is L*(L+1)*(2L+1)/6.

    Args:
        params: TyreParameters instance.
        stint_length: Duration of the stint in laps.
        initial_age: Age of the tyre set at stint start (e.g. used tyres).

    Returns:
        Total expected tyre contribution time in seconds.
    """
    if stint_length <= 0:
        return 0.0

    # Effective ages: (initial_age + 1) to (initial_age + stint_length)
    laps = np.arange(initial_age + 1, initial_age + stint_length + 1)
    sum_k = float(np.sum(laps))
    sum_k2 = float(np.sum(laps**2))

    linear_cost = params.alpha * stint_length + params.beta * sum_k
    cliff_cost = params.gamma * sum_k2
    return float(linear_cost + cliff_cost)


def generate_ar1_noise(
    n_laps: int,
    sigma: float,
    rho: float,
    seed: int | None = None,
) -> NDArray[np.float64]:
    """Generate autocorrelated AR(1) race lap pace deviations.

    Models dirty air, tyre thermal cycles, and micro-lockups where
    a slow lap tends to correlate with subsequent pace.

    Args:
        n_laps: Number of laps to generate.
        sigma: Unconditional standard deviation (s).
        rho: Lag-1 autocorrelation (-1 < rho < 1).
        seed: Random seed for reproducibility.

    Returns:
        Array of length n_laps with zero-mean AR(1) noise.
    """
    rng = np.random.default_rng(seed)
    noise = np.zeros(n_laps, dtype=np.float64)
    if n_laps == 0:
        return noise

    noise[0] = rng.normal(0, sigma)
    shock_std = sigma * np.sqrt(max(0.0, 1.0 - rho**2))

    for t in range(1, n_laps):
        noise[t] = rho * noise[t - 1] + rng.normal(0, shock_std)

    return noise
