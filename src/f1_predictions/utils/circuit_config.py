"""Circuit-specific configuration loader for the F1 2026 prediction pipeline.

Rationale:
    The ML model and pipeline need circuit-specific knowledge that cannot be
    inferred from the lap telemetry alone (e.g., Monaco's near-zero overtake
    probability, its 78-lap race distance, 22s pit loss time). Hard-coding these
    values in master_pipeline.py is fragile and untestable. This module provides
    a typed, Pydantic-validated interface to ``configs/config.yaml``.

Design decisions:
    - Pydantic v2 BaseModel: consistent with project's existing pydantic-settings
      usage; provides field-level validation with descriptive error messages.
    - YAML source: ``configs/config.yaml`` is the single source of truth.
    - Graceful fallback: unknown circuit names return the ``defaults`` block from
      the YAML rather than raising an exception; the pipeline must be resilient
      to new calendar additions.
    - Module-level cache: the YAML is parsed once per process and cached; avoids
      repeated disk I/O in the feature pipeline's per-session loops.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────

# Resolve relative to this file's location so the module works regardless of
# the current working directory (important for Trigger.dev cloud workers).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH: Path = _REPO_ROOT / "configs" / "config.yaml"


# ── Pydantic schema ────────────────────────────────────────────────────────────


class CircuitConfig(BaseModel):
    """Typed representation of a single circuit's configuration profile.

    Attributes:
        base_lap_time_s: Nominal dry-weather pole-lap reference time (seconds).
            Used as a normalisation anchor for lap-delta features.
        total_laps: Official race distance in laps.
        overtake_difficulty: Scalar 0.0 (trivial) → 1.0 (impossible).
            Encodes how much qualifying grid position determines finishing order.
            Derived from historical overtake frequency per circuit.
        tyre_wear_type: Dominant tyre degradation mechanism.
            ``"thermal"`` — sustained high-speed cornering degrades surface rubber.
            ``"mechanical"`` — low-speed heavy-braking zones wear carcass structure.
        safety_car_probability: Historical VSC/SC deployment rate (0.0-1.0).
        pit_loss_time_s: Average time delta lost per pit stop in seconds
            (pit entry + stop + exit, incl. speed-limiter penalty).
        typical_strategy: Dominant 1-stop compound sequence (ordered list).
        alt_strategy: Alternate strategy (2-stop or soft-start).
        drs_zones: Number of DRS activation zones on the circuit.
        circuit_type: ``"street"`` | ``"permanent"`` | ``"hybrid"``.
    """

    base_lap_time_s: float = Field(
        gt=0.0, description="Reference pole lap time in seconds"
    )
    total_laps: int = Field(gt=0, description="Official race lap count")
    overtake_difficulty: float = Field(
        ge=0.0, le=1.0, description="0=easy overtaking, 1=impossible"
    )
    tyre_wear_type: str = Field(description="'thermal' or 'mechanical'")
    safety_car_probability: float = Field(
        ge=0.0, le=1.0, description="Historical SC/VSC deployment rate"
    )
    pit_loss_time_s: float = Field(
        gt=0.0, description="Average pit stop time loss in seconds"
    )
    typical_strategy: list[str] = Field(
        min_length=1, description="Dominant compound sequence"
    )
    alt_strategy: list[str] = Field(
        min_length=1, description="Alternate strategy compound sequence"
    )
    drs_zones: int = Field(ge=0, description="Number of DRS zones")
    circuit_type: str = Field(description="'street', 'permanent', or 'hybrid'")

    @field_validator("tyre_wear_type")
    @classmethod
    def validate_tyre_wear_type(cls, v: str) -> str:
        """Enforce valid tyre wear type values."""
        valid = {"thermal", "mechanical"}
        if v not in valid:
            msg = f"tyre_wear_type must be one of {valid}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("circuit_type")
    @classmethod
    def validate_circuit_type(cls, v: str) -> str:
        """Enforce valid circuit type values."""
        valid = {"street", "permanent", "hybrid"}
        if v not in valid:
            msg = f"circuit_type must be one of {valid}, got '{v}'"
            raise ValueError(msg)
        return v

    @property
    def is_street_circuit(self) -> bool:
        """Return True if this is a street circuit (Monaco, Singapore, etc.)."""
        return self.circuit_type == "street"

    @property
    def strategy_label(self) -> str:
        """Return a human-readable strategy label, e.g. 'M→H'."""
        return "→".join(c[0] for c in self.typical_strategy)


# ── YAML loader (cached) ───────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _load_yaml() -> dict[str, Any]:
    """Load and parse the circuit config YAML exactly once per process.

    Returns:
        Parsed YAML as a nested dict.

    Raises:
        FileNotFoundError: If ``configs/config.yaml`` does not exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    if not _CONFIG_PATH.exists():
        msg = f"Circuit config not found at: {_CONFIG_PATH}"
        raise FileNotFoundError(msg)

    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    logger.debug("Circuit config loaded from %s", _CONFIG_PATH)
    return data


# ── Public API ─────────────────────────────────────────────────────────────────


def get_circuit_config(event_name: str) -> CircuitConfig:
    """Return the circuit configuration for the given GP event name.

    Performs a case-insensitive substring match against the YAML keys so that
    minor naming differences (e.g. "Monaco GP" vs. "Monaco Grand Prix") are
    handled gracefully. If no match is found, the ``defaults`` block from the
    YAML is returned with a warning log — this ensures the pipeline never
    crashes on a new circuit not yet in the registry.

    Args:
        event_name: FastF1 event name string (e.g. ``"Monaco Grand Prix"``).

    Returns:
        A validated ``CircuitConfig`` instance.

    Example::

        cfg = get_circuit_config("Monaco Grand Prix")
        print(cfg.total_laps)          # 78
        print(cfg.overtake_difficulty) # 0.95
        print(cfg.strategy_label)     # M→H
    """
    data = _load_yaml()
    circuits: dict[str, Any] = data.get("circuits", {})
    defaults: dict[str, Any] = data.get("defaults", {})

    # Exact match first
    if event_name in circuits:
        raw = circuits[event_name]
        logger.info("Circuit config matched (exact): '%s'", event_name)
        return CircuitConfig(**raw)

    # Case-insensitive fuzzy match based on the first word
    # (usually the country/city name) handles "Monaco GP" → "Monaco Grand Prix"
    event_parts = event_name.lower().split()
    if event_parts:
        first_word = event_parts[0]
        for key, raw in circuits.items():
            if first_word in key.lower():
                logger.info(
                    "Circuit config matched (fuzzy): '%s' → '%s'", event_name, key
                )
                return CircuitConfig(**raw)

    # Fallback to defaults — do NOT raise; log a warning instead
    logger.warning(
        "No circuit config found for '%s'. Using default profile. "
        "Add this circuit to configs/config.yaml for precise modelling.",
        event_name,
    )
    return CircuitConfig(**defaults)


def list_configured_circuits() -> list[str]:
    """Return all circuit names currently registered in the YAML.

    Returns:
        Sorted list of circuit event name strings.
    """
    data = _load_yaml()
    return sorted(data.get("circuits", {}).keys())
