"""Virtual race simulation script: predict performance hierarchy for a specific GP."""

import argparse
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from f1_predictions.features.external_weather import (
    WeatherIntelligence,
    simulation_weather_features,
)
from f1_predictions.features.historical_performance import add_ewma_form_features
from f1_predictions.features.traffic_exposure import CLEAN_AIR_SCENARIO
from f1_predictions.models import (
    LightGBMPaceRegressor,
    StackingPaceRegressor,
)
from f1_predictions.models.common import prepare_feature_matrix
from f1_predictions.utils.analysis import build_driver_standings, build_predictions_df
from f1_predictions.utils.circuit_config import get_circuit_config
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)

# Cross-driver quantities that enter the model as pooled season medians, and whose
# spread therefore carries the window's track mix. Their deviations are replaced
# with per-circuit deltas in _apply_track_pace_normalization.
#
# Sector times are proportional to lap time, so once the field's level is moved onto
# the target circuit's scale their deviations follow the same ratio. Speeds are not
# proportional to lap time, so their deviations are left in raw km/h.
_SECTOR_PACE_FEATURES: tuple[str, ...] = (
    "Sector1Time_s",
    "Sector2Time_s",
    "Sector3Time_s",
)
_SPEED_PACE_FEATURES: tuple[str, ...] = ("SpeedI1", "SpeedI2", "SpeedFL", "SpeedST")
_DEVIATION_NORMALIZED_FEATURES: tuple[str, ...] = (
    _SECTOR_PACE_FEATURES + _SPEED_PACE_FEATURES
)


def _enrich_with_track_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Join track characteristics metadata with the main DataFrame.

    Args:
        df: Input DataFrame containing EventName.

    Returns:
        DataFrame enriched with numeric track features.
    """
    settings = get_settings()
    meta_path = settings.data_external_dir / "track_metadata.csv"

    if not meta_path.exists():
        logger.warning(
            "Track metadata not found at %s. Skipping enrichment.", meta_path
        )
        return df

    meta_df = pd.read_csv(meta_path)

    # Encode categorical features numerically for the GBM
    type_map = {"Street": 1, "Permanent": 2, "Hybrid": 3}
    df_map = {"Ultra-Low": 1, "Low": 2, "Medium": 3, "High": 4, "Ultra-High": 5}

    meta_df["TrackType_val"] = meta_df["TrackType"].map(type_map).fillna(0)
    meta_df["DownforceLevel_val"] = meta_df["DownforceLevel"].map(df_map).fillna(0)

    # Merge on EventName (standardised in both files)
    enriched_df = df.merge(
        meta_df[
            [
                "EventName",
                "TrackType_val",
                "DownforceLevel_val",
                "Abrasiveness",
                "FullThrottlePct",
                "AvgSpeed_kph",
                "MaxSpeed_kph",
                "CornerCount",
            ]
        ],
        on="EventName",
        how="left",
    )

    # Fill NaNs for tracks not in metadata
    fill_cols = [
        "TrackType_val",
        "DownforceLevel_val",
        "Abrasiveness",
        "FullThrottlePct",
        "AvgSpeed_kph",
        "MaxSpeed_kph",
        "CornerCount",
    ]
    enriched_df[fill_cols] = enriched_df[fill_cols].fillna(0)

    # Populate circuit_config parameters
    if "EventName" in enriched_df.columns:
        for col in ["streetness", "speed_bias", "overtaking_ease", "tyre_stress"]:
            if col not in enriched_df.columns:
                enriched_df[col] = 0.5
        unique_events = enriched_df["EventName"].dropna().unique()
        for evt in unique_events:
            cfg = get_circuit_config(str(evt))
            mask = enriched_df["EventName"] == evt
            enriched_df.loc[mask, "streetness"] = cfg.streetness
            enriched_df.loc[mask, "speed_bias"] = cfg.speed_bias
            enriched_df.loc[mask, "overtaking_ease"] = cfg.overtaking_ease
            enriched_df.loc[mask, "tyre_stress"] = cfg.tyre_stress

    return enriched_df


def _driver_track_normalized_deltas(
    df_current: pd.DataFrame, is_wet_race: bool, value_column: str = "LapTime_s"
) -> pd.Series:
    """Per-driver delta in seconds, weighting every circuit equally.

    A driver's median pooled across a season mostly measures *which* circuits they
    have laps at: the current-season window mixes tracks whose lap times differ by
    more than ten seconds, so a driver who retired at a short circuit ends up
    seconds per lap "faster" than a team-mate who did not. The same applies to any
    quantity measured per lap, which is why ``value_column`` is a parameter: sector
    times and speeds are pooled medians with exactly this artefact.

    Reference every lap to its own round's median instead, reduce each driver to
    one observation per round, then take the median across rounds. Lap counts at
    any single circuit can no longer flatter or punish anyone.

    Args:
        df_current: Current-season laps, one row per lap.
        is_wet_race: Whether to restrict to wet or dry laps.
        value_column: Column to measure. Defaults to lap time.

    Returns:
        Median delta to the round baseline, indexed by driver. Empty when there
        is nothing to measure.
    """
    if value_column not in df_current.columns:
        return pd.Series(dtype="float64")

    laps = df_current.dropna(subset=[value_column]).copy()
    if "Rainfall" in laps.columns and not laps["Rainfall"].isna().all():
        matching = laps[laps["Rainfall"] == is_wet_race]
        if not matching.empty:
            laps = matching
    if laps.empty:
        return pd.Series(dtype="float64")

    key = "RoundNumber" if "RoundNumber" in laps.columns else "EventName"
    laps["_round_median"] = laps.groupby(key)[value_column].transform("median")
    laps["_delta"] = laps[value_column] - laps["_round_median"]

    per_round = laps.groupby(["Driver", key], as_index=False)["_delta"].median()
    return per_round.groupby("Driver")["_delta"].median()


# A published field spread is only meaningful if the measured laps support it. Feeding
# the model pooled sector medians made it publish 1.32x the measured spread; correcting
# that brought it to 1.00x. Anything above this band means the window's track mix is
# leaking back into the predictions, which is the failure this check exists to catch.
MAX_SPREAD_INFLATION: float = 1.25


def check_published_dispersion(
    predicted_spread_s: float, measured_spread_s: float
) -> float:
    """Compare the spread about to be published against the spread the laps show.

    The current-season window puts a hard floor under how far apart two drivers can
    legitimately be, because that spread *is* measured pace. When the model publishes
    materially more separation than the laps show, something other than pace is driving
    the fit.

    Args:
        predicted_spread_s: Fastest-to-slowest spread across the predictions.
        measured_spread_s: Fastest-to-slowest spread across the measured deltas.

    Returns:
        The inflation ratio, or ``nan`` when there is nothing to measure against.
    """
    if not np.isfinite(measured_spread_s) or measured_spread_s <= 0:
        logger.warning(
            "Dispersion check skipped: no lap-measured pace spread for this window."
        )
        return float("nan")

    ratio = float(predicted_spread_s / measured_spread_s)
    message = "Published field spread %.3fs vs lap-measured %.3fs (%.2fx)"
    if ratio > MAX_SPREAD_INFLATION:
        logger.warning(
            "%s -- above the %.2fx band; the pace normalization may be leaking the "
            "window's track mix into the predictions.",
            message % (predicted_spread_s, measured_spread_s, ratio),
            MAX_SPREAD_INFLATION,
        )
    else:
        logger.info(message, predicted_spread_s, measured_spread_s, ratio)
    return ratio


def _apply_track_pace_normalization(
    df_sim: pd.DataFrame,
    event_name: str,
    gold_all: pd.DataFrame,
    df_current: pd.DataFrame,
    is_wet_race: bool = False,
) -> pd.DataFrame:
    """Translate cross-track pace onto the target circuit's lap-time scale.

    The simulation's pace features are season medians, so they sit at the
    current-season window's level (e.g. 95s) rather than the target circuit's
    (e.g. Canada ~78s).

    Math:
        Driver_Delta  = median over rounds of (lap - that round's median lap)
        Target_Pace   = Track_Historical_Baseline + Driver_Delta
        Sector_Target = Field_Sector_Level * ratio + Driver_Sector_Delta * ratio
        Speed_Target  = Field_Speed_Level + Driver_Speed_Delta
        ratio         = Track_Historical_Baseline / Window_Median

    The driver delta is measured per round and then averaged, so the mix of
    circuits in the window cannot masquerade as pace (see
    _driver_track_normalized_deltas). That applies to the sector and speed columns
    too: they arrive as season medians pooled across the same mixed window, so a
    driver's value mostly reflects which circuits they have laps at. Only the
    field-wide level is carried over from the window; every driver-specific
    deviation is re-measured per circuit.
    """
    # 1. Get current season global baseline
    season_global_median = df_current["LapTime_s"].median()

    # 2. Get target track historical baseline
    track_laps = gold_all[
        gold_all["EventName"].str.contains(event_name, case=False, na=False)
    ]

    # Filter by weather conditions to avoid wet/dry skew
    if "Rainfall" in track_laps.columns and not track_laps["Rainfall"].isna().all():
        cond_laps = track_laps[track_laps["Rainfall"] == is_wet_race]
        if not cond_laps.empty:
            track_laps = cond_laps
        else:
            logger.warning(
                "No historical %s laps for '%s', using all available laps.",
                "wet" if is_wet_race else "dry",
                event_name,
            )
    else:
        logger.warning(
            "Rainfall column missing or all NaN, cannot split baseline by weather."
        )

    if track_laps.empty:
        logger.warning(
            "No historical data for '%s', falling back to season median", event_name
        )
        track_baseline = season_global_median
    else:
        track_baseline = track_laps["LapTime_s"].median()

    # 3. Driver pace, measured per circuit so the window's track mix cannot
    #    masquerade as pace.
    deltas = _driver_track_normalized_deltas(df_current, is_wet_race)
    fallback_delta = float(deltas.median()) if len(deltas) else 0.0
    if not np.isfinite(fallback_delta):
        fallback_delta = 0.0
    spread = float(deltas.max() - deltas.min()) if len(deltas) else 0.0

    logger.info(
        "Pace normalization for %s: Historical Baseline = %.3fs, Current Season Global = %.3fs, driver delta spread = %.3fs",
        event_name,
        track_baseline,
        season_global_median,
        spread,
    )

    # Sectors are season medians too, so the field's level follows the
    # window-to-track ratio: one scale for the whole field, not one per driver.
    sector_scale = (
        track_baseline / season_global_median if season_global_median > 0 else 1.0
    )

    df = df_sim.copy()
    for idx, row in df.iterrows():
        driver_delta = float(deltas.get(row["Driver"], fallback_delta))
        if not np.isfinite(driver_delta):
            driver_delta = fallback_delta
        target_lap_pace = track_baseline + driver_delta

        for col in ("roll_laptime_3", "roll_laptime_5"):
            if col in df.columns:
                df.at[idx, col] = target_lap_pace

    # Sector and speed columns carry the same pooled-median artefact as lap time.
    # Measured on the current window, Sector2's cross-driver spread correlated with
    # lap-count mix at -0.71 against +0.19 with measured pace, and feeding the pooled
    # values to the model published a 6.5s field spread where the laps support 4.9s.
    # Keep the field's level (scaled to the target circuit for sectors) and rebuild
    # every driver deviation from their own per-circuit measurements.
    for column in _DEVIATION_NORMALIZED_FEATURES:
        if column not in df.columns:
            continue
        is_sector = column in _SECTOR_PACE_FEATURES
        ratio = sector_scale if is_sector else 1.0
        field_level = float(df_sim[column].mean()) * ratio
        column_deltas = _driver_track_normalized_deltas(
            df_current, is_wet_race, value_column=column
        )
        for idx, row in df.iterrows():
            delta = (
                float(column_deltas.get(row["Driver"], 0.0))
                if len(column_deltas)
                else 0.0
            )
            if not np.isfinite(delta):
                delta = 0.0
            df.at[idx, column] = field_level + delta * ratio

    return df


def _calculate_sample_weights(
    df: pd.DataFrame, target_year: int, target_round: int
) -> pd.Series:
    """Calculate exponential decay weights based on race recency.

    Rationale: F1 is a development-heavy sport. Form from 2 months ago is
    less relevant than the last race. This weighting helps the model
    capture 'momentum' and recent technical upgrades.

    Formula: weight = exp(-decay * distance_in_rounds)
    """
    # Calculate distance in rounds (approximate across years)
    # Assume 24 rounds per year for distance calculation
    df["round_dist"] = (target_year - df["Season"]) * 24 + (
        target_round - df["RoundNumber"]
    )

    # Decay factor: weight halves every 10 rounds (~half a season)
    decay_rate = 0.07  # exp(-0.07 * 10) approx 0.5
    weights = np.exp(-decay_rate * df["round_dist"])

    # Normalise weights so mean is 1.0 (standard practice for GBMs)
    return cast(pd.Series, weights / weights.mean())


def _apply_weather_scenario_features(
    df_sim: pd.DataFrame,
    *,
    is_wet_race: bool,
    weather_intelligence: WeatherIntelligence | None = None,
) -> pd.DataFrame:
    """Apply Friday forecast weather assumptions to simulation rows.

    The historical training matrix already contains FastF1 weather features.
    Before race sessions exist, this function fills equivalent feature columns
    for the simulated race scenario from external forecast intelligence.
    """
    df = df_sim.copy()
    values = simulation_weather_features(weather_intelligence, is_wet_race=is_wet_race)
    for column, value in values.items():
        df[column] = value
    return df


def _align_scenario_one_hot_features(
    df_sim: pd.DataFrame, df_train: pd.DataFrame
) -> pd.DataFrame:
    """Populate one-hot dummy columns in df_sim matching df_train.

    In the Gold parquet dataset, categorical columns (Compound, Team, EventName)
    are already one-hot encoded (e.g. ``Compound_MEDIUM``, ``Team_Ferrari``,
    ``EventName_Monaco Grand Prix``). The simulation scenario builds raw string
    columns, which on naive concatenation leaves all dummy columns as NaN for
    the simulated rows, causing tree regressors to take missing-value branches.

    This helper assigns 1.0/0.0 values to every dummy column present in
    ``df_train`` by matching against the raw string column in ``df_sim``.
    Unknown categories (e.g. a newly added circuit) naturally map to all zeros,
    honouring ``handle_unknown="ignore"``.

    Args:
        df_sim: Simulation scenario DataFrame containing raw string columns.
        df_train: Training DataFrame with pre-encoded dummy columns.

    Returns:
        DataFrame with aligned one-hot dummy columns.
    """
    df = df_sim.copy()
    prefixes = [
        ("Compound_", "Compound"),
        ("Team_", "Team"),
        ("EventName_", "EventName"),
    ]
    for prefix, raw_col in prefixes:
        if raw_col not in df.columns:
            continue
        dummy_cols = [c for c in df_train.columns if c.startswith(prefix)]
        for dc in dummy_cols:
            val = dc[len(prefix) :]
            df[dc] = (df[raw_col].astype(str) == val).astype(float)
    return df


def _round_number(path: Path) -> int | None:
    """Parse the round number from a ``round=NN`` partition path."""
    for part in path.parts:
        if part.startswith("round="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _gold_files_before_round(
    data_dir: Path, year: int, round_number: int
) -> list[Path]:
    """Return the season's Gold files for rounds strictly before ``round_number``.

    A pre-race prediction may use the current season's completed rounds, never
    the round being predicted (or anything after it). The live path never sees
    those files because they do not exist yet, but a backtest does — without
    this filter a walk-forward run silently reads the answer.
    """
    files = sorted(data_dir.glob(f"season={year}/**/*.parquet"))
    return [
        path
        for path in files
        if (parsed := _round_number(path)) is None or parsed < round_number
    ]


def _current_form_stats(df_current: pd.DataFrame) -> pd.DataFrame:
    """Collapse the season-so-far laps into one form row per driver.

    Args:
        df_current: Every Gold lap of the season being simulated.

    Returns:
        One row per driver holding the median of each pace feature, the points
        position going into the race, and the team.
    """
    return (
        df_current.groupby("Driver")
        .agg(
            {
                "SpeedI1": "median",
                "SpeedI2": "median",
                "SpeedFL": "median",
                "SpeedST": "median",
                "Sector1Time_s": "median",
                "Sector2Time_s": "median",
                "Sector3Time_s": "median",
                "LapTime_s": "median",
                "roll_std_3": "median",
                "delta_roll_pace": "median",
                "tyre_deg_slope": "median",
                "tyre_life_norm": "median",
                "DriverPointsPreRace": "max",
                "TeamPointsPreRace": "max",
                "Team": "first",
            }
        )
        .reset_index()
    )


def _build_simulation_scenario(
    driver_stats: pd.DataFrame,
    year: int,
    round_number: int,
    event_name: str,
    lap_number: int,
) -> pd.DataFrame:
    """Build the simulated clean-air lap, one row per driver.

    The scenario describes a lap that has not been raced yet: mid-race point, ten
    laps into a stint on the medium tyre, mid-field. Its traffic-exposure labels are
    not an afterthought — they are what turns "a lap" into "a clean-air lap".

    Args:
        driver_stats: One row per driver holding the current-season form values.
        year: Season year being simulated.
        round_number: Round number being simulated.
        event_name: Event name, stored for metadata and reporting.
        lap_number: Hypothetical lap number to simulate.

    Returns:
        One row per driver, ready for enrichment and normalisation.
    """
    sim_data: list[dict[str, Any]] = []

    for driver in driver_stats["Driver"].unique():
        d_info = driver_stats[driver_stats["Driver"] == driver].iloc[0]
        # NOTE: MADRID_PUBLISHED_PRIOR is deliberately *not* fed in as
        # clean_air_pace_delta_s / clean_air_confidence. Those columns exist only in
        # this scenario and in no training row, so the trees can never split on them
        # and they changed nothing (verified: zeroing them leaves predictions
        # byte-identical). A feature that is present at inference and absent in
        # training is train/serve skew, not signal.
        #
        # The traffic-exposure labels are the opposite case and are fed in: every
        # training row carries a measured value, so the trees *can* split on them,
        # and this lap is by definition a clean-air lap. Serving the measured
        # clean-air medians keeps the scenario row inside the region the model was
        # trained on instead of at an extrapolated extreme.
        sim_data.append(
            {
                "Season": year,
                "RoundNumber": round_number,
                "EventName": event_name,
                "Driver": driver,
                "Team": d_info["Team"],
                "LapNumber": lap_number,
                "Stint": 1,
                "TyreLife": 10,
                "Compound": "MEDIUM",
                "Position": 5,
                **CLEAN_AIR_SCENARIO,
                "DriverPointsPreRace": d_info["DriverPointsPreRace"],
                "TeamPointsPreRace": d_info["TeamPointsPreRace"],
                "SpeedI1": d_info["SpeedI1"],
                "SpeedI2": d_info["SpeedI2"],
                "SpeedFL": d_info["SpeedFL"],
                "SpeedST": d_info["SpeedST"],
                "Sector1Time_s": d_info["Sector1Time_s"],
                "Sector2Time_s": d_info["Sector2Time_s"],
                "Sector3Time_s": d_info["Sector3Time_s"],
                "roll_laptime_3": d_info["LapTime_s"],
                "roll_laptime_5": d_info["LapTime_s"],
                "roll_std_3": d_info["roll_std_3"],
                "delta_roll_pace": d_info["delta_roll_pace"],
                "tyre_deg_slope": d_info["tyre_deg_slope"],
                "tyre_life_norm": d_info["tyre_life_norm"],
                "PitInTime_s": 0,
                "PitOutTime_s": 0,
                "LapTime_s": 0,
            }
        )

    return pd.DataFrame(sim_data)


def run_race_simulation(
    year: int,
    round_number: int,
    event_name: str,
    lap_number: int = 15,
    is_wet_race: bool = False,
    weather_intelligence: WeatherIntelligence | None = None,
) -> None:
    """Run a virtual race simulation with statistical rigor (Phase 2).

    Args:
        year: The season year to simulate.
        round_number: The round number of the event.
        event_name: The full name of the Grand Prix.
        lap_number: The hypothetical lap number to simulate (default 15).
    """
    settings = get_settings()
    safe_event = event_name.replace(" ", "_")

    # 1. Load historical/current season data
    data_dir = Path(settings.data_outputs_dir) / "laps"
    gold_files = _gold_files_before_round(data_dir, year, round_number)

    if not gold_files:
        logger.error(
            "No data found for season %d in %s. Please ingest previous rounds first.",
            year,
            data_dir,
        )
        return

    df_current = pd.concat([pd.read_parquet(f) for f in gold_files])

    # 2. Calculate driver-specific metrics for current form
    logger.info(
        "Calculating current form for %d season (up to round %d)...",
        year,
        round_number,
    )
    driver_stats = _current_form_stats(df_current)

    # 3. Build simulation scenario (Virtual Lap)
    drivers = driver_stats["Driver"].unique()
    df_sim = _build_simulation_scenario(
        driver_stats, year, round_number, event_name, lap_number
    )

    # 4. Train Models on Historical Data (2022 to year-1)
    train_years = list(range(2022, year))
    if not train_years:
        train_years = [2022, 2023, 2024, 2025]

    # Load and enrich
    gold_all_files = list(data_dir.glob("season=[2-9]*/**/*.parquet"))
    gold_all = pd.concat([pd.read_parquet(f) for f in gold_all_files])
    df_train_full = gold_all[gold_all["Season"].isin(train_years)]

    # ENRICH with track metadata & EWMA features
    logger.info("Enriching data and calculating temporal weights...")
    df_train_full = _enrich_with_track_metadata(df_train_full)
    df_sim = _enrich_with_track_metadata(df_sim)

    # Add EWMA form features
    df_sim = add_ewma_form_features(df_sim)
    df_train_full = add_ewma_form_features(df_train_full)

    # APPLY track pace normalization to simulation scenario.
    logger.info(
        "Normalizing cross-track driver paces to '%s' %s baseline...",
        event_name,
        "wet" if is_wet_race else "dry",
    )
    df_sim = _apply_track_pace_normalization(
        df_sim, event_name, df_train_full, df_current, is_wet_race=is_wet_race
    )
    df_sim = _apply_weather_scenario_features(
        df_sim,
        is_wet_race=is_wet_race,
        weather_intelligence=weather_intelligence,
    )
    df_sim = _align_scenario_one_hot_features(df_sim, df_train_full)

    # Calculate Weights (Phase 2.2)
    sample_weights = _calculate_sample_weights(df_train_full, year, round_number)

    # Prepare features
    df_combined = pd.concat([df_train_full, df_sim], ignore_index=True)
    x_all, _ = prepare_feature_matrix(df_combined, require_target=False)

    x_train = x_all.iloc[: -len(drivers)].drop(columns=["Season"], errors="ignore")
    y_train = df_train_full["LapTime_s"]
    x_sim = x_all.tail(len(drivers)).drop(columns=["Season"], errors="ignore")

    # 5. Training Suite (Phase 2.1: Quantile Regression)
    logger.info("Training Quantile Regression suite (P05, P50, P95)...")

    # StackingRegressor as the new baseline (mean)
    stack_model = StackingPaceRegressor()
    cast(Any, stack_model.model).fit(x_train, y_train, sample_weight=sample_weights)
    y_pred_baseline = cast(Any, stack_model.model).predict(x_sim)

    # Tripwire: the published spread must be the one the laps support.
    measured_deltas = _driver_track_normalized_deltas(df_current, is_wet_race)
    check_published_dispersion(
        float(np.max(y_pred_baseline) - np.min(y_pred_baseline)),
        float(measured_deltas.max() - measured_deltas.min())
        if len(measured_deltas)
        else float("nan"),
    )

    # LightGBM Quantile Models
    quantiles = [0.05, 0.50, 0.95]
    quantile_preds = {}

    for q in quantiles:
        logger.info("Fitting LightGBM for alpha=%.2f...", q)
        lgb_q = LightGBMPaceRegressor(alpha=q)
        cast(Any, lgb_q.model).fit(x_train, y_train, sample_weight=sample_weights)
        quantile_preds[q] = cast(Any, lgb_q.model).predict(x_sim)

    # 6. Save Results
    res_dir = Path(settings.reports_dir) / str(year) / safe_event / "results"
    res_dir.mkdir(parents=True, exist_ok=True)

    metadata = df_sim[["Season", "RoundNumber", "EventName", "Driver", "Team"]]
    predictions_df = build_predictions_df(
        metadata, y_pred_baseline, quantile_preds
    ).sort_values("predicted_laptime_xgb_s")

    # Save CSVs
    standings = build_driver_standings(predictions_df)
    standings.to_csv(res_dir / "standings.csv", index=False)
    predictions_df.to_csv(res_dir / "predictions.csv", index=False)

    logger.info("Simulation complete! Results with uncertainty saved to: %s", res_dir)
    print(f"\nVirtual Race Prediction for {event_name} ({year}) finished successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a virtual F1 race simulation.")
    parser.add_argument("--year", type=int, default=2026, help="Season year")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument(
        "--event", type=str, required=True, help="Event name (e.g. 'Miami Grand Prix')"
    )
    parser.add_argument(
        "--weather",
        type=str,
        choices=["dry", "wet"],
        default="dry",
        help="Simulate the race under dry or wet conditions (default: dry)",
    )
    parser.add_argument(
        "--lap", type=int, default=15, help="Hypothetical lap number to simulate"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()
    configure_root_pipeline_logger(level=args.log_level)

    run_race_simulation(
        year=args.year,
        round_number=args.round,
        event_name=args.event,
        lap_number=args.lap,
        is_wet_race=args.weather == "wet",
    )
