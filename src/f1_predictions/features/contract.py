"""Canonical feature contract shared by the local and Databricks paths.

Task 21.3 bridges two Gold schemas that were previously unrelated:

* the local per-lap Gold (``data/outputs/laps``), which targets ``LapTime_s``;
* the Unity Catalog per-driver Gold (``driver_features_gold``), which targets
  ``fastest_lap_seconds``.

The bridge is additive. It does **not** change the published simulation path or
the aggregate registry champion. It defines a small, versioned, pre-lap-safe
feature set that both engines can compute, and exposes it as a new opt-in DLT
table (``lap_features_gold``) and training schema (``--training-schema lap``).

The feature set is deliberately narrower than the 70-feature local matrix. A
column belongs here only if it is:

1. computable from the DLT Silver columns,
2. known **before** the lap is driven, and
3. numerically defined identically in Pandas and Spark (pinned by
   ``tests/unit/test_lap_features_spark.py``).

Columns that fail (1) or (2) are recorded in :data:`NON_BRIDGE_FEATURES` rather
than silently copied into a model that would then look better than it is. The
local 70-feature model still uses several of them; that is a pre-existing,
documented limitation, not a property this contract endorses.

Version history:
    1 — initial bridge: 13 pre-lap features, causal rolling pace and
        cumulative prior-best delta, no NaN imputation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# bump whenever LAP_FEATURES or a feature's definition changes. The DLT table
# stamps this value and training refuses a table with a different version.
FEATURE_CONTRACT_VERSION: Final[int] = 1
VERSION_COLUMN: Final[str] = "feature_contract_version"

# ---------------------------------------------------------------------------
# Lap-level (local + Databricks) schema
# ---------------------------------------------------------------------------

LAP_TABLE: Final[str] = "lap_features_gold"
LAP_TARGET: Final[str] = "LapTime_s"
LAP_MODEL_NAME: Final[str] = "xgb_lap_pace_regressor"

LAP_KEYS: Final[tuple[str, ...]] = (
    "Season",
    "RoundNumber",
    "EventName",
    "Driver",
    "LapNumber",
    "Stint",
)

# Context columns are carried for joins/analysis. They are not model features:
# `Position` is assigned by FastF1 after the lap is complete, `SessionType` is
# constant (the table is race-only), and `Team`/`Compound` are identities.
LAP_CONTEXT_COLUMNS: Final[tuple[str, ...]] = (
    "Compound",
    "Team",
    "Position",
    "SessionType",
)

LAP_FEATURES: Final[tuple[str, ...]] = (
    "LapNumber",
    "Stint",
    "TyreLife",
    "roll_laptime_3",
    "roll_laptime_5",
    "roll_std_3",
    "delta_roll_pace",
    "delta_to_fastest_s",
    "Compound_SOFT",
    "Compound_MEDIUM",
    "Compound_HARD",
    "Compound_INTERMEDIATE",
    "Compound_WET",
)

# GroupKFold is by event, never by lap: laps from the same race share tyres,
# weather and track state, so a random lap split would leak the answer.
LAP_CV_GROUP_COLUMNS: Final[tuple[str, ...]] = ("Season", "RoundNumber")

# ---------------------------------------------------------------------------
# Aggregate (existing Unity Catalog champion) schema
# ---------------------------------------------------------------------------

AGGREGATE_TABLE: Final[str] = "driver_features_gold"
AGGREGATE_TARGET: Final[str] = "fastest_lap_seconds"
AGGREGATE_MODEL_NAME: Final[str] = "xgb_race_pace_regressor"

AGGREGATE_KEYS: Final[tuple[str, ...]] = ("Season", "EventName", "Driver")
AGGREGATE_FEATURES: Final[tuple[str, ...]] = (
    "total_laps",
    "mean_pace_seconds",
    "pace_std_seconds",
    "tyre_degradation_slope",
)


@dataclass(frozen=True)
class TrainingSchema:
    """Everything a training or prediction run needs to resolve a Gold table.

    Attributes:
        name: CLI name (``aggregate`` or ``lap``).
        table: Unqualified Unity Catalog table name.
        target: Regression target column.
        features: Ordered model feature columns.
        keys: Row identity columns used for prediction output.
        model_name: Base Unity Catalog model name. The lap and aggregate lanes
            intentionally use different names so their RMSEs are never compared.
        fill_missing_features: ``True`` only for the legacy aggregate path,
            which historically filled missing aggregates with ``0.0``. The lap
            path leaves NaN intact so XGBoost can use its missing-value branch;
            a zero-filled rolling mean would fabricate a 0-second prior lap.
        cv_group_columns: Columns that define an independent CV group. ``None``
            keeps the legacy 3-fold split.
        contract_version: Expected value of ``feature_contract_version``.
            ``None`` means the table predates the shared contract.
    """

    name: str
    table: str
    target: str
    features: tuple[str, ...]
    keys: tuple[str, ...]
    model_name: str
    fill_missing_features: bool
    cv_group_columns: tuple[str, ...] | None = None
    contract_version: int | None = None


AGGREGATE_SCHEMA: Final[TrainingSchema] = TrainingSchema(
    name="aggregate",
    table=AGGREGATE_TABLE,
    target=AGGREGATE_TARGET,
    features=AGGREGATE_FEATURES,
    keys=AGGREGATE_KEYS,
    model_name=AGGREGATE_MODEL_NAME,
    fill_missing_features=True,
)

LAP_SCHEMA: Final[TrainingSchema] = TrainingSchema(
    name="lap",
    table=LAP_TABLE,
    target=LAP_TARGET,
    features=LAP_FEATURES,
    keys=LAP_KEYS,
    model_name=LAP_MODEL_NAME,
    fill_missing_features=False,
    cv_group_columns=LAP_CV_GROUP_COLUMNS,
    contract_version=FEATURE_CONTRACT_VERSION,
)

TRAINING_SCHEMAS: Final[dict[str, TrainingSchema]] = {
    AGGREGATE_SCHEMA.name: AGGREGATE_SCHEMA,
    LAP_SCHEMA.name: LAP_SCHEMA,
}

# Local features intentionally kept out of the v1 bridge. Keys are exact column
# names; the one-hot families are described in `docs/ARCHITECTURE.md` §3.4.
NON_BRIDGE_FEATURES: Final[dict[str, str]] = {
    "Position": "FastF1 assigns it after the lap is complete (end-of-lap order).",
    "tyre_deg_slope": "Full-stint OLS uses laps after t (prospective).",
    "tyre_life_norm": "Full-stint min-max needs the stint's final TyreLife.",
    "Sector1Time_s": "Measured during the current lap.",
    "Sector2Time_s": "Measured during the current lap.",
    "Sector3Time_s": "Measured during the current lap.",
    "SpeedI1": "Measured during the current lap.",
    "SpeedI2": "Measured during the current lap.",
    "SpeedFL": "Measured during the current lap.",
    "SpeedST": "Measured during the current lap.",
    "PitInTime_s": "Known only when the lap ends in the pit lane.",
    "PitOutTime_s": "Known only when the lap starts in the pit lane.",
    "traffic_ahead_s": "Local telemetry reconstruction; absent from DLT Silver.",
    "traffic_nearest_s": "Local telemetry reconstruction; absent from DLT Silver.",
    "DriverPointsPreRace": "Local results-derived; absent from DLT Silver.",
    "TeamPointsPreRace": "Local results-derived; absent from DLT Silver.",
    "Season": "Identity key; excluded from features to avoid event memorisation.",
    "RoundNumber": "Identity key; excluded from features to avoid event memorisation.",
    "Compound_None": "Encoder artifact for missing compounds; no signal.",
    "Compound_nan": "Encoder artifact for missing compounds; no signal.",
}


def resolve_training_schema(name: str | None = None) -> TrainingSchema:
    """Return a :class:`TrainingSchema` by CLI name.

    Args:
        name: ``aggregate``, ``lap``, or ``None`` for the historical default.

    Returns:
        The matching immutable schema.

    Raises:
        ValueError: If ``name`` is not a known schema.
    """
    requested = (name or AGGREGATE_SCHEMA.name).strip().lower()
    try:
        return TRAINING_SCHEMAS[requested]
    except KeyError as exc:
        choices = ", ".join(sorted(TRAINING_SCHEMAS))
        msg = f"Unknown training schema '{name}'. Choose one of: {choices}."
        raise ValueError(msg) from exc


def validate_feature_frame(
    frame: object,
    schema: TrainingSchema,
    *,
    require_target: bool = True,
    require_version: bool = True,
) -> None:
    """Fail fast when a frame does not carry the schema's required columns.

    This is a structural check only; it deliberately does not import pandas so
    the DLT module can share the contract. Version *values* are checked by
    :func:`f1_predictions.features.training_data.prepare_training_data`, which
    operates on a pandas frame.

    Args:
        frame: Any frame-like object exposing a ``columns`` attribute.
        schema: Schema whose keys, features and (optionally) target must exist.
        require_target: Require the target column (training) or not (scoring).
        require_version: Require ``feature_contract_version`` when the schema
            declares a contract version. Pass ``False`` for the local Gold,
            which predates the version stamp.

    Raises:
        TypeError: If ``frame`` does not expose ``columns``.
        ValueError: If any required column is absent.
    """
    columns = getattr(frame, "columns", None)
    if columns is None:
        msg = (
            "Expected a frame-like object with a 'columns' attribute, got "
            f"{type(frame).__name__}."
        )
        raise TypeError(msg)

    required: list[str] = [*schema.keys, *schema.features]
    if require_target:
        required.append(schema.target)
    if schema.cv_group_columns:
        required.extend(schema.cv_group_columns)
    if require_version and schema.contract_version is not None:
        required.append(VERSION_COLUMN)

    present = set(columns)
    missing = [column for column in dict.fromkeys(required) if column not in present]
    if missing:
        msg = (
            f"{schema.name} feature frame is missing required column(s): {missing}. "
            f"Expected the shared contract (v{schema.contract_version or 'legacy'}) "
            f"on table '{schema.table}'."
        )
        raise ValueError(msg)
