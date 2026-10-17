"""Post-race prediction accuracy verdict engine.

Computes the "Monday Verdict" — a structured accuracy report comparing
the ML model's pre-race predictions against the official FastF1 results.

Design decisions:
    - Uses a dataclass (RaceVerdict) rather than a dict to enforce a typed
      contract between this module and the notification system. Mypy --strict
      will catch any downstream type mismatches at import time.
    - Verdict computation is separated from I/O: load_predictions() and
      load_actuals() are isolated, making them individually testable.
    - No side effects in compute_verdict() — pure function on DataFrames.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fastf1
import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Columns expected in the predictions CSV (Gold layer output of master_pipeline).
_PRED_COLS: list[str] = ["Driver", "Predicted_LapTime_s", "Predicted_Position"]


@dataclass
class RaceVerdict:
    """Structured accuracy report for a single race weekend.

    Attributes:
        round: F1 round number (1-24).
        gp_name: Full Grand Prix name (e.g. 'Monaco Grand Prix').
        mae_lap_time_s: Mean Absolute Error of predicted lap times (seconds).
        mape_pct: Mean Absolute Percentage Error of lap time predictions (%).
        winner_correct: True if the predicted P1 matches the actual P1.
        podium_accuracy_pct: % of podium finishers (P1-P3) correctly predicted.
        top10_accuracy_pct: % of top-10 finishers correctly predicted.
        key_misses: List of drivers where prediction error was highest.
        status: 'excellent' | 'good' | 'needs_improvement' based on MAE.
    """

    round: int
    gp_name: str
    mae_lap_time_s: float
    mape_pct: float
    winner_correct: bool
    podium_accuracy_pct: float
    top10_accuracy_pct: float
    key_misses: list[str] = field(default_factory=list)
    # Accuracy classification. Left as "unknown" it is derived from MAE in
    # __post_init__; an explicit value ("preview", "unavailable", …) is
    # preserved so notifications that carry no measured accuracy are never
    # mislabelled as a real result.
    status: str = "unknown"

    def __post_init__(self) -> None:
        """Classify accuracy status from MAE unless one was set explicitly."""
        if self.status != "unknown":
            return
        if self.mae_lap_time_s < 0.200:
            self.status = "excellent"
        elif self.mae_lap_time_s < 0.350:
            self.status = "good"
        else:
            self.status = "needs_improvement"

    def to_dict(self) -> dict[str, object]:
        """Serialize verdict to a JSON-serializable dict for reporting.

        Returns:
            Dict representation of the verdict.
        """
        return {
            "round": self.round,
            "gp_name": self.gp_name,
            "mae_lap_time_s": round(self.mae_lap_time_s, 4),
            "mape_pct": round(self.mape_pct, 2),
            "winner_correct": self.winner_correct,
            "podium_accuracy_pct": round(self.podium_accuracy_pct, 1),
            "top10_accuracy_pct": round(self.top10_accuracy_pct, 1),
            "key_misses": self.key_misses,
            "status": self.status,
        }


def load_predictions(predictions_path: Path) -> pd.DataFrame:
    """Load the model's pre-race predictions from the Gold layer CSV.

    Args:
        predictions_path: Absolute path to the predictions CSV file.

    Returns:
        DataFrame with driver abbreviations, predicted lap times, and
        predicted finishing positions.

    Raises:
        FileNotFoundError: If the predictions file does not exist.
        ValueError: If required columns are missing.
    """
    if not predictions_path.exists():
        msg = f"Predictions file not found: {predictions_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(predictions_path)
    if "predicted_laptime_xgb_s" in df.columns:
        df = df.rename(columns={"predicted_laptime_xgb_s": "Predicted_LapTime_s"})
    if "Predicted_Position" not in df.columns and "Predicted_LapTime_s" in df.columns:
        df["Predicted_Position"] = (
            df["Predicted_LapTime_s"].rank(method="min").astype(int)
        )

    missing = [c for c in _PRED_COLS if c not in df.columns]
    if missing:
        msg = f"Predictions CSV missing required columns: {missing}"
        raise ValueError(msg)

    logger.debug("Loaded %d prediction rows from %s", len(df), predictions_path)
    return df


def load_actuals(season: int, round_number: int) -> pd.DataFrame:
    """Fetch official race results from FastF1 for a given round.

    Uses the Race session results which are available ~2h after the
    chequered flag. Returns a DataFrame indexed by driver abbreviation.

    Args:
        season: F1 season year.
        round_number: Race round number (1-24).

    Returns:
        DataFrame with driver abbreviations, finishing positions, and
        fastest lap times.

    Raises:
        RuntimeError: If FastF1 cannot load the session results.
    """
    logger.info(
        "Fetching actual results from FastF1: %d Round %d", season, round_number
    )
    try:
        session = fastf1.get_session(season, round_number, "R")
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        results: pd.DataFrame = session.results[["Abbreviation", "Position"]].copy()

        # Fastest-lap times are an *optional* enrichment: the timing feed can be
        # unavailable (blocked, rate-limited, or still propagating) even when
        # finishing positions are already known. Missing lap data must never
        # abort the verdict — positional accuracy remains valid without it.
        try:
            laps = session.laps
        except Exception as laps_exc:
            logger.warning(
                "Lap-timing data unavailable for %d R%d (%s); "
                "computing positional accuracy only.",
                season,
                round_number,
                laps_exc,
            )
            laps = None

        fastest_laps = (
            laps.groupby("Driver")["LapTime"].min().reset_index()
            if laps is not None and not laps.empty
            else None
        )
        if fastest_laps is not None:
            fastest_laps = fastest_laps.rename(
                columns={
                    "Driver": "Abbreviation",
                    "LapTime": "FastestLapTime",
                }
            )
            results = results.merge(
                fastest_laps,
                on="Abbreviation",
                how="left",
            )
        else:
            results["FastestLapTime"] = pd.NaT
        results["Position"] = results["Position"].astype(int)
        logger.info("Loaded actual results for %d drivers", len(results))
    except Exception as exc:
        msg = f"Failed to load FastF1 results for {season} R{round_number}: {exc}"
        raise RuntimeError(msg) from exc
    else:
        return results


def compute_verdict(
    predictions: pd.DataFrame,
    actuals: pd.DataFrame,
    round_number: int,
    gp_name: str,
) -> RaceVerdict:
    """Compute prediction accuracy by joining predictions to actual results.

    Joins on driver abbreviation, computes MAE/MAPE on lap times, and
    evaluates positional accuracy at winner, podium, and top-10 levels.

    Args:
        predictions: Output of `load_predictions`.
        actuals: Output of `load_actuals`.
        round_number: Race round number for the verdict label.
        gp_name: Grand Prix name for the verdict label.

    Returns:
        A fully populated `RaceVerdict` dataclass.
    """
    # Inner join on driver abbreviation — only evaluate drivers in both sets.
    merged = predictions.merge(
        actuals,
        left_on="Driver",
        right_on="Abbreviation",
        how="inner",
    )

    if merged.empty:
        logger.warning("No driver overlap between predictions and actuals.")
        return RaceVerdict(
            round=round_number,
            gp_name=gp_name,
            mae_lap_time_s=999.0,
            mape_pct=999.0,
            winner_correct=False,
            podium_accuracy_pct=0.0,
            top10_accuracy_pct=0.0,
            key_misses=[],
        )

    # ── Lap time accuracy ─────────────────────────────────────────────────
    # FastestLapTime is a timedelta when laps loaded; an all-NaT placeholder
    # column arrives as datetime64 (or object), which pd.to_timedelta rejects.
    # Guard the conversion so a lap-less actuals frame cannot crash the verdict.
    raw_lap_times = merged["FastestLapTime"]
    if pd.api.types.is_timedelta64_dtype(raw_lap_times):
        merged["Actual_LapTime_s"] = raw_lap_times.dt.total_seconds()
    else:
        merged["Actual_LapTime_s"] = pd.Series(float("nan"), index=merged.index)
    merged["abs_error"] = (
        merged["Predicted_LapTime_s"] - merged["Actual_LapTime_s"]
    ).abs()
    # Timing data (FastestLapTime) may be entirely absent even when finishing
    # positions are known. In that case emit a positional-only verdict with an
    # explicit "partial" status rather than a NaN MAE that would be silently
    # misclassified as "needs_improvement" by the MAE-based classifier.
    lap_time_available = bool(
        merged["Actual_LapTime_s"].notna().any()
        and merged["Predicted_LapTime_s"].notna().any()
    )
    if lap_time_available:
        mae = float(merged["abs_error"].mean())
        mape = float((merged["abs_error"] / merged["Actual_LapTime_s"] * 100).mean())
        key_misses: list[str] = merged.nlargest(3, "abs_error")["Driver"].tolist()
        verdict_status = "unknown"
    else:
        logger.warning(
            "Lap-timing data unavailable for %s (R%d); "
            "emitting positional-only verdict.",
            gp_name,
            round_number,
        )
        mae = float("nan")
        mape = float("nan")
        key_misses = []
        verdict_status = "partial"

    # ── Positional accuracy ───────────────────────────────────────────────
    predicted_winner = merged.sort_values("Predicted_Position").iloc[0]["Driver"]
    actual_winner = merged.sort_values("Position").iloc[0]["Abbreviation"]
    winner_correct = predicted_winner == actual_winner

    pred_podium = set(merged.nsmallest(3, "Predicted_Position")["Driver"].tolist())
    actual_podium = set(merged.nsmallest(3, "Position")["Abbreviation"].tolist())
    podium_accuracy = len(pred_podium & actual_podium) / 3.0 * 100.0

    pred_top10 = set(merged.nsmallest(10, "Predicted_Position")["Driver"].tolist())
    actual_top10 = set(merged.nsmallest(10, "Position")["Abbreviation"].tolist())
    top10_accuracy = len(pred_top10 & actual_top10) / 10.0 * 100.0

    logger.info(
        "Verdict: MAE=%.4fs | MAPE=%.2f%% | Winner=%s | Podium=%.0f%% | status=%s",
        mae,
        mape,
        "✓" if winner_correct else "✗",
        podium_accuracy,
        verdict_status,
    )

    return RaceVerdict(
        round=round_number,
        gp_name=gp_name,
        mae_lap_time_s=mae,
        mape_pct=mape,
        winner_correct=winner_correct,
        podium_accuracy_pct=podium_accuracy,
        top10_accuracy_pct=top10_accuracy,
        key_misses=key_misses,
        status=verdict_status,
    )
