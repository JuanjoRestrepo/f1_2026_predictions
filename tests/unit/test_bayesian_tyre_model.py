"""Unit tests for the Bayesian quadratic tyre degradation model and solver."""

import numpy as np

from f1_predictions.features.bayesian_tyre_model import (
    TyreParameters,
    fit_quadratic_degradation,
    generate_ar1_noise,
    remove_fuel_effect,
    solve_closed_form_stint_cost,
)


def test_remove_fuel_effect() -> None:
    """Test fuel weight stripping isolates pure tyre degradation."""
    total_laps = 50
    current_laps = np.array([1, 25, 50], dtype=np.int64)
    # Hypothetical constant observed pace (tire deg balances fuel burn)
    observed_laps = np.array([80.0, 80.0, 80.0], dtype=np.float64)

    zero_fuel = remove_fuel_effect(
        observed_laps,
        current_laps,
        total_laps,
        starting_fuel_kg=92.5,
        reserve_fuel_kg=3.0,
        weight_effect_s_per_kg=0.03,
    )

    # Lap 1: full fuel (~92.5kg = 2.775s), lap 50: reserve only (0.09s)
    # Zero-fuel lap times reveal early laps were inherently faster
    assert zero_fuel[0] < zero_fuel[-1]


def test_fit_quadratic_degradation() -> None:
    """Fit quadratic parameters alpha, beta, gamma to synthetic wear."""
    laps = np.arange(1, 25, dtype=np.int64)
    true_alpha, true_beta, true_gamma = 75.0, 0.05, 0.002
    clean_wear = true_alpha + true_beta * laps + true_gamma * (laps**2)

    alpha, beta, gamma = fit_quadratic_degradation(laps, clean_wear)

    assert np.isclose(alpha, true_alpha, atol=1e-2)
    assert np.isclose(beta, true_beta, atol=1e-3)
    assert np.isclose(gamma, true_gamma, atol=1e-4)


def test_solve_closed_form_stint_cost() -> None:
    """Check closed-form analytical stint sum matches loop sum."""
    params = TyreParameters(
        compound="MEDIUM",
        alpha=80.0,
        beta=0.04,
        gamma=0.001,
        sigma=0.3,
        rho=0.35,
        max_life=35.0,
    )

    stint_len = 20
    analytical_cost = solve_closed_form_stint_cost(params, stint_len, initial_age=0)

    # Numerical verification
    manual_cost = sum(params.expected_lap_time(k) for k in range(1, stint_len + 1))
    assert np.isclose(analytical_cost, manual_cost)


def test_generate_ar1_noise() -> None:
    """Verify AR(1) noise statistics and stationarity."""
    n_laps = 500
    sigma = 0.35
    rho = 0.40
    noise = generate_ar1_noise(n_laps, sigma=sigma, rho=rho, seed=42)

    assert len(noise) == n_laps
    assert np.abs(np.mean(noise)) < 0.1
    # Sample std should approximate unconditional sigma
    assert np.isclose(np.std(noise), sigma, atol=0.08)
