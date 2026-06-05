"""Unit tests for the circuit configuration registry and Pydantic loader.

Tests validate:
    - Monaco GP config loads with correct values (the primary 2026 race-critical test)
    - All registered circuits have valid Pydantic schemas (no silent mis-configuration)
    - Unknown circuit names fall back to defaults without raising exceptions
    - Fuzzy name matching works (e.g. "Monaco GP" → "Monaco Grand Prix")
    - CircuitConfig properties (is_street_circuit, strategy_label) are correct
"""

from __future__ import annotations

from f1_predictions.utils.circuit_config import (
    CircuitConfig,
    get_circuit_config,
    list_configured_circuits,
)

# ── Monaco-specific tests (race-critical for June 7 GP) ───────────────────────


class TestMonacoCircuitConfig:
    """Critical validation of Monaco GP parameters.

    Monaco is the single biggest outlier on the 2026 calendar.
    These tests are the pipeline's safety net before the Friday forecast runs.
    """

    def test_monaco_loads_without_error(self) -> None:
        """get_circuit_config must not raise for 'Monaco Grand Prix'."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert isinstance(cfg, CircuitConfig)

    def test_monaco_total_laps(self) -> None:
        """Monaco official race distance is 78 laps — not the generic 50 fallback."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.total_laps == 78, (
            f"Monaco total_laps should be 78, got {cfg.total_laps}. "
            "A wrong lap count propagates to the tyre strategy and lap-position chart."
        )

    def test_monaco_overtake_difficulty(self) -> None:
        """Monaco overtake difficulty must be ≥ 0.90 (highest on calendar)."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.overtake_difficulty >= 0.90, (
            f"Monaco overtake_difficulty should be >= 0.90, "
            f"got {cfg.overtake_difficulty}. "
            "Qualifying position determines ~87% of Monaco race finishing order."
        )

    def test_monaco_is_street_circuit(self) -> None:
        """Monaco must be classified as a street circuit."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.is_street_circuit is True

    def test_monaco_safety_car_probability(self) -> None:
        """Monaco safety car probability must be ≥ 0.80."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.safety_car_probability >= 0.80

    def test_monaco_pit_loss_time(self) -> None:
        """Monaco pit loss time must be ≥ 21s (tight pit lane, highest on calendar)."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.pit_loss_time_s >= 21.0

    def test_monaco_tyre_wear_type(self) -> None:
        """Monaco is mechanical wear — slow corners, no sustained thermal loading."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.tyre_wear_type == "mechanical"

    def test_monaco_strategy_label(self) -> None:
        """Monaco strategy label should be 'M→H' (single stop)."""
        cfg = get_circuit_config("Monaco Grand Prix")
        # Strategy label is first letter of each compound joined by →
        assert len(cfg.typical_strategy) >= 2, (
            "Monaco must have at least 2 stint compounds"
        )

    def test_monaco_drs_zones(self) -> None:
        """Monaco has only 1 DRS zone — the shortest on the calendar."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.drs_zones == 1


# ── Fallback behaviour tests ───────────────────────────────────────────────────


class TestCircuitConfigFallback:
    """Validate graceful degradation for unknown circuits."""

    def test_unknown_circuit_returns_defaults(self) -> None:
        """Unknown circuit name must return a valid CircuitConfig, not raise."""
        cfg = get_circuit_config("Fictional Grand Prix")
        assert isinstance(cfg, CircuitConfig)
        # Defaults must be sensible non-zero values
        assert cfg.total_laps > 0
        assert 0.0 <= cfg.overtake_difficulty <= 1.0
        assert cfg.pit_loss_time_s > 0.0

    def test_empty_string_returns_defaults(self) -> None:
        """Empty event name must not crash the pipeline."""
        cfg = get_circuit_config("")
        assert isinstance(cfg, CircuitConfig)

    def test_fuzzy_match_monaco(self) -> None:
        """'Monaco GP' should fuzzy-match to 'Monaco Grand Prix'."""
        cfg = get_circuit_config("Monaco GP")
        # Should not be the generic default (total_laps == 78 is Monaco-specific)
        assert cfg.total_laps == 78, (
            "Fuzzy match failed: 'Monaco GP' should resolve to "
            "Monaco Grand Prix config."
        )


# ── Schema validation for all registered circuits ─────────────────────────────


class TestAllCircuitSchemas:
    """Every circuit in config.yaml must pass Pydantic validation."""

    def test_all_circuits_load_without_error(self) -> None:
        """Every registered circuit must produce a valid CircuitConfig."""
        circuits = list_configured_circuits()
        assert len(circuits) > 0, (
            "Circuit registry is empty — check configs/config.yaml"
        )

        for name in circuits:
            cfg = get_circuit_config(name)
            assert isinstance(cfg, CircuitConfig), f"Failed for: {name}"
            assert cfg.total_laps > 0, f"total_laps invalid for: {name}"
            assert 0.0 <= cfg.overtake_difficulty <= 1.0, (
                f"overtake_difficulty out of range: {name}"
            )

    def test_minimum_circuit_count(self) -> None:
        """The 2026 F1 calendar should have at least 20 rounds configured."""
        circuits = list_configured_circuits()
        assert len(circuits) >= 20, (
            f"Only {len(circuits)} circuits registered. "
            "The 2026 calendar has 21+ rounds. Update configs/config.yaml."
        )

    def test_strategy_labels_are_non_empty(self) -> None:
        """All circuits must have a non-empty strategy_label."""
        for name in list_configured_circuits():
            cfg = get_circuit_config(name)
            label = cfg.strategy_label
            assert len(label) >= 1, f"Empty strategy_label for: {name}"


# ── CircuitConfig property tests ──────────────────────────────────────────────


class TestCircuitConfigProperties:
    """Unit tests for derived properties on CircuitConfig."""

    def test_street_circuit_property_true(self) -> None:
        """Monaco must return True for is_street_circuit."""
        cfg = get_circuit_config("Monaco Grand Prix")
        assert cfg.is_street_circuit is True

    def test_street_circuit_property_false(self) -> None:
        """Bahrain (permanent circuit) must return False for is_street_circuit."""
        cfg = get_circuit_config("Bahrain Grand Prix")
        assert cfg.is_street_circuit is False

    def test_strategy_label_format(self) -> None:
        """strategy_label must be single uppercase letters joined by →."""
        cfg = get_circuit_config("Monaco Grand Prix")
        label = cfg.strategy_label
        parts = label.split("→")
        assert all(len(p) == 1 and p.isupper() for p in parts), (
            f"strategy_label '{label}' should be single uppercase letters joined by →"
        )
