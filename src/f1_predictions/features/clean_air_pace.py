"""Clean-air long-run race pace extraction module.

Extracts representative FP2 long-run race pace from FastF1 timing data, filtering
out traffic interference, driver lockup errors, and applying Bayesian prior
shrinkage for optimal prediction performance on new or semi-street circuits.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FastF1Session(Protocol):
    """Protocol representing a FastF1 Session with laps attribute."""

    laps: pd.DataFrame


REFERENCE_LAP_SECONDS: float = 101.0

# Published priors for Madrid GP / new circuit baseline (Compound/fuel adjusted)
# Updated for 2026 season form (Antonelli WDC leader, Hadjar at Red Bull)
MADRID_PUBLISHED_PRIOR: dict[str, tuple[float, float]] = {
    "RUS": (0.00, 1.00),
    "VER": (0.10, 0.95),
    "ANT": (0.20, 0.95),
    "NOR": (0.35, 0.85),
    "PIA": (0.40, 0.85),
    "HAD": (0.45, 0.75),
    "HAM": (0.50, 0.85),
    "LEC": (0.50, 0.85),
    "LAW": (0.65, 0.60),
    "OCO": (0.92, 0.80),
    "BEA": (0.92, 0.55),
    "GAS": (1.20, 0.70),
    "LIN": (1.25, 0.40),
    "TSU": (1.25, 0.40),
    "COL": (1.40, 0.55),
    "HUL": (1.80, 0.60),
    "BOR": (1.80, 0.60),
    "ALB": (2.10, 0.60),
    "SAI": (2.10, 0.60),
    "PER": (3.50, 0.55),
    "BOT": (3.50, 0.55),
    "ALO": (3.80, 0.55),
    "STR": (3.80, 0.40),
}


def prepare_laps(session: FastF1Session) -> pd.DataFrame:
    """Prepare timing interval columns for lap-by-lap traffic evaluation."""
    laps = session.laps.copy()
    laps["lap_seconds"] = laps["LapTime"].dt.total_seconds()
    laps["start_seconds"] = laps["LapStartTime"].dt.total_seconds()
    laps["end_seconds"] = laps["Time"].dt.total_seconds()
    return laps


def active_intervals(laps: pd.DataFrame) -> dict[str, np.ndarray]:
    """Create on-track lap intervals used to infer traffic and nearby cars."""
    intervals: dict[str, np.ndarray] = {}
    for driver, group in laps.groupby("Driver"):
        duration = group["end_seconds"] - group["start_seconds"]
        valid = group[
            group["start_seconds"].notna()
            & group["end_seconds"].notna()
            & duration.between(60.0, 180.0)
            & group["PitOutTime"].isna()
            & group["PitInTime"].isna()
        ].sort_values("start_seconds")
        intervals[str(driver)] = valid[
            ["LapNumber", "start_seconds", "end_seconds"]
        ].to_numpy(dtype=float)
    return intervals


def traffic_margins(
    driver: str,
    lap_number: float,
    start: float,
    end: float,
    intervals: dict[str, np.ndarray],
) -> tuple[float, float]:
    """Return minimum estimated seconds to car ahead and nearest car on track."""
    samples = (0.20, 0.40, 0.60, 0.80)
    ahead_samples: list[float] = []
    nearest_samples: list[float] = []

    for fraction in samples:
        timestamp = start + fraction * (end - start)
        focal_progress = (lap_number - 1.0) + fraction
        min_ahead = float("inf")
        min_nearest = float("inf")

        for other_driver, values in intervals.items():
            if other_driver == driver or values.size == 0:
                continue
            active = values[(values[:, 1] <= timestamp) & (values[:, 2] >= timestamp)]
            if not len(active):
                continue
            other_lap, other_start, other_end = active[0]
            if (other_end - other_start) <= 0:
                continue
            fraction_complete = (timestamp - other_start) / (other_end - other_start)
            other_progress = (other_lap - 1.0) + fraction_complete
            forward_fraction = (other_progress - focal_progress) % 1.0
            min_ahead = min(min_ahead, forward_fraction * REFERENCE_LAP_SECONDS)
            min_nearest = min(
                min_nearest,
                min(forward_fraction, 1.0 - forward_fraction) * REFERENCE_LAP_SECONDS,
            )

        ahead_samples.append(min_ahead)
        nearest_samples.append(min_nearest)

    return float(min(ahead_samples)), float(min(nearest_samples))


def candidate_long_run_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Select late-session race runs and label traffic at the lap level."""
    intervals = active_intervals(laps)
    records: list[dict[str, Any]] = []

    for (driver, stint), raw_stint in laps.groupby(["Driver", "Stint"]):
        timed = raw_stint[raw_stint["LapTime"].notna()].copy()
        if len(timed) < 4:
            continue

        usable = timed[
            timed["IsAccurate"].fillna(False)
            & timed["PitOutTime"].isna()
            & timed["PitInTime"].isna()
            & (timed["TrackStatus"] == "1")
            & (timed["lap_seconds"] < 130.0)
        ].sort_values("LapNumber")

        if len(usable) < 3:
            continue

        for stint_index, (_, lap) in enumerate(usable.iterrows(), start=1):
            ahead, nearest = traffic_margins(
                str(driver),
                float(lap["LapNumber"]),
                float(lap["start_seconds"]),
                float(lap["end_seconds"]),
                intervals,
            )
            records.append(
                {
                    "driver": str(driver),
                    "stint": int(cast(Any, stint)),
                    "compound": str(lap.get("Compound", "MEDIUM")),
                    "lap_number": int(lap["LapNumber"]),
                    "tyre_life": float(lap.get("TyreLife", 1)),
                    "stint_index": stint_index,
                    "lap_seconds": float(lap["lap_seconds"]),
                    "ahead_margin_s": ahead,
                    "nearest_margin_s": nearest,
                    "clean_air": ahead >= 2.0 and nearest >= 1.2,
                }
            )

    return pd.DataFrame(records)


def reject_driver_errors(clean_laps: pd.DataFrame) -> pd.DataFrame:
    """Remove lockup or mistake laps using robust Median Absolute Deviation (MAD)."""
    kept: list[pd.DataFrame] = []
    for _, stint in clean_laps.groupby(["driver", "stint"]):
        if stint.empty:
            continue
        minimum = stint["lap_seconds"].min()
        median = stint["lap_seconds"].median()
        mad = np.median(np.abs(stint["lap_seconds"] - median))
        robust_ceiling = median + max(1.25, 3.0 * 1.4826 * mad)
        absolute_ceiling = minimum + 3.25
        kept.append(
            stint[stint["lap_seconds"] <= min(robust_ceiling, absolute_ceiling)]
        )
    return pd.concat(kept, ignore_index=True) if kept else clean_laps.iloc[0:0]


def robust_spread(values: pd.Series) -> float:
    """Compute robust MAD spread of lap times."""
    if len(values) < 2:
        return 0.0
    median = np.median(values)
    return float(1.4826 * np.median(np.abs(values - median)))


def summarize_clean_air(
    candidates: pd.DataFrame, priors: dict[str, tuple[float, float]] | None = None
) -> pd.DataFrame:
    """Summarize clean air long-run pace per driver with Bayesian prior shrinkage."""
    if candidates.empty:
        logger.warning("No FP2 long-run laps passed candidate filter.")
        return pd.DataFrame()

    clean = reject_driver_errors(candidates[candidates["clean_air"]].copy())
    if clean.empty:
        clean = candidates.copy()

    if priors is None:
        priors = MADRID_PUBLISHED_PRIOR

    summaries: list[dict[str, Any]] = []
    for driver, all_laps in candidates.groupby("driver"):
        driver_str = str(driver)
        driver_clean = clean[clean["driver"] == driver_str]
        if driver_clean.empty:
            driver_clean = all_laps

        pace = float(driver_clean["lap_seconds"].median())
        spread = robust_spread(driver_clean["lap_seconds"])
        clean_count = len(driver_clean)
        candidate_count = len(all_laps)
        coverage = clean_count / max(candidate_count, 1)

        confidence = min(clean_count / 6.0, 1.0)
        confidence *= float(np.exp(-spread / 1.5))
        confidence *= 0.50 + 0.50 * coverage
        confidence = float(np.clip(confidence, 0.0, 0.80))

        compound_mode = (
            driver_clean["compound"].mode().iloc[0]
            if not driver_clean["compound"].empty
            else "MEDIUM"
        )

        prior_delta, prior_conf = priors.get(driver_str, (1.50, 0.50))

        # Bayesian combination of observed clean air delta & prior
        model_confidence = max(confidence, prior_conf)
        weight_obs = confidence / (confidence + prior_conf + 1e-5)
        raw_delta = pace - clean["lap_seconds"].min()
        blended_delta = weight_obs * raw_delta + (1.0 - weight_obs) * prior_delta

        summaries.append(
            {
                "driver": driver_str,
                "compound": compound_mode,
                "clean_air_pace_s": pace,
                "clean_laps": clean_count,
                "candidate_laps": candidate_count,
                "clean_air_spread_s": spread,
                "timing_confidence": confidence,
                "raw_clean_air_delta_s": raw_delta,
                "published_prior_delta_s": prior_delta,
                "model_clean_air_delta_s": blended_delta,
                "model_clean_air_confidence": model_confidence,
            }
        )

    df_res = pd.DataFrame(summaries)
    if not df_res.empty:
        ref_val = df_res["model_clean_air_delta_s"].min()
        df_res["model_clean_air_delta_s"] = df_res["model_clean_air_delta_s"] - ref_val

    return df_res


def add_published_prior(summary: pd.DataFrame) -> pd.DataFrame:
    """Shrink noisy timing estimates toward fuel/compound-adjusted reporting."""
    observed = summary.set_index("driver").to_dict("index") if not summary.empty else {}
    rows: list[dict[str, Any]] = []
    for driver, (prior_delta, prior_confidence) in MADRID_PUBLISHED_PRIOR.items():
        item = observed.get(driver)
        if item is None:
            rows.append(
                {
                    "driver": driver,
                    "compound": "NO REPRESENTATIVE RUN",
                    "clean_air_pace_s": np.nan,
                    "clean_laps": 0,
                    "candidate_laps": 0,
                    "traffic_rejected_laps": 0,
                    "clean_air_spread_s": np.nan,
                    "median_ahead_margin_s": np.nan,
                    "timing_confidence": 0.0,
                    "raw_clean_air_delta_s": np.nan,
                    "published_prior_delta_s": prior_delta,
                    "published_prior_confidence": prior_confidence,
                    "model_clean_air_delta_s": prior_delta,
                    "model_clean_air_confidence": prior_confidence,
                }
            )
            continue
        else:
            obs_delta = item.get("raw_clean_air_delta_s", prior_delta)
            if pd.isna(obs_delta):
                obs_delta = prior_delta
            obs_conf = float(item.get("timing_confidence", 0.0))
            denom = obs_conf + prior_confidence + 1e-5
            w_obs = obs_conf / denom
            model_delta = float(w_obs * obs_delta + (1.0 - w_obs) * prior_delta)
            model_conf = float(max(obs_conf, prior_confidence))

            row = dict(item)
            row["driver"] = driver
            row["published_prior_delta_s"] = prior_delta
            row["published_prior_confidence"] = prior_confidence
            row["model_clean_air_delta_s"] = model_delta
            row["model_clean_air_confidence"] = model_conf
            rows.append(row)

    df_out = pd.DataFrame(rows)
    if not df_out.empty and "model_clean_air_delta_s" in df_out.columns:
        valid = df_out["model_clean_air_delta_s"].dropna()
        if not valid.empty:
            ref = float(valid.min())
            df_out["model_clean_air_delta_s"] = df_out["model_clean_air_delta_s"] - ref
    return df_out
