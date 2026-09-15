"""Historical performance features for the f1_predictions pipeline.

Rationale:
    Pace alone does not capture the full context of a race. Drivers and teams
    carrying momentum (high championship points) often have preferential strategy
    calls, better reliability, and a psychological edge.

    This module computes the cumulative championship points for drivers and
    constructors BEFORE the start of the current session. This avoids
    data leakage (we cannot use points earned IN the current race to predict
    the current race).
"""

import numpy as np
import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def add_historical_points(
    df: pd.DataFrame,
    df_history_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add cumulative championship points for drivers and teams.

    Args:
        df: Clean laps or results DataFrame to enrich.
        df_history_results: Concatenated results DataFrame from all previous
            rounds in the current season. Must contain `Abbreviation`,
            `TeamName`, and `Points`. If None or empty, points are set to 0
            (e.g., Round 1 of the season).

    Returns:
        New DataFrame with ``DriverPointsPreRace`` and ``TeamPointsPreRace`` appended.

    Raises:
        TypeError: If inputs are not pandas DataFrames.
        KeyError: If required columns are missing.
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected df to be pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    result = df.copy()

    col_driver_pts = "DriverPointsPreRace"
    col_team_pts = "TeamPointsPreRace"

    if df_history_results is None or df_history_results.empty:
        logger.info("No historical results provided (Round 1?). Setting points to 0.")
        result[col_driver_pts] = 0.0
        result[col_team_pts] = 0.0
        return result

    required_cols = ["Abbreviation", "TeamName", "Points"]
    missing = [c for c in required_cols if c not in df_history_results.columns]
    if missing:
        msg = f"Required column(s) missing from df_history_results: {missing}"
        raise KeyError(msg)

    # Compute cumulative points
    driver_points = df_history_results.groupby("Abbreviation")["Points"].sum().to_dict()
    team_points = df_history_results.groupby("TeamName")["Points"].sum().to_dict()

    # Map to current dataframe
    # If the df is laps, the driver identifier is 'Driver'.
    # If results, it is 'Abbreviation'.
    driver_col = "Driver" if "Driver" in result.columns else "Abbreviation"
    team_col = "Team" if "Team" in result.columns else "TeamName"

    if driver_col not in result.columns or team_col not in result.columns:
        logger.warning(
            "Driver/Team identifier columns not found in target DataFrame. "
            "Available: %s. Setting points to 0.",
            list(result.columns),
        )
        result[col_driver_pts] = 0.0
        result[col_team_pts] = 0.0
        return result

    result[col_driver_pts] = (
        result[driver_col].map(driver_points).fillna(0.0).astype("float32")
    )
    result[col_team_pts] = (
        result[team_col].map(team_points).fillna(0.0).astype("float32")
    )

    logger.info(
        "Historical points features added: %s, %s",
        col_driver_pts,
        col_team_pts,
    )
    return result


def ewma(values: list[float], default: float = 10.0, alpha: float = 0.45) -> float:
    """Compute recent-weighted mean without looking beyond the current round."""
    if not values:
        return default
    estimate = values[0]
    for value in values[1:]:
        estimate = alpha * value + (1.0 - alpha) * estimate
    return float(estimate)


def add_ewma_form_features(
    df: pd.DataFrame,
    df_history_results: pd.DataFrame | None = None,
    alpha: float = 0.45,
) -> pd.DataFrame:
    """Compute EWMA form features for drivers and teams across past rounds.

    Args:
        df: Target DataFrame to enrich with EWMA features.
        df_history_results: Historical results DataFrame sorted by RoundNumber.
        alpha: Smoothing factor for EWMA (default 0.45).

    Returns:
        DataFrame enriched with driver_finish_ewma, team_finish_ewma,
        team_points_ewma, driver_dnf_rate.
    """
    result = df.copy()

    col_driver = "Driver" if "Driver" in result.columns else "Abbreviation"
    col_team = "Team" if "Team" in result.columns else "TeamName"

    if (
        df_history_results is None
        or df_history_results.empty
        or col_driver not in result.columns
    ):
        result["driver_finish_ewma"] = 11.0
        result["team_finish_ewma"] = 11.0
        result["team_points_ewma"] = 0.0
        result["driver_dnf_rate"] = 0.05
        return result

    # Sort history chronologically
    history = df_history_results.sort_values("RoundNumber")

    driver_finishes: dict[str, list[float]] = {}
    team_finishes: dict[str, list[float]] = {}
    team_pts_hist: dict[str, list[float]] = {}
    driver_dnfs: dict[str, list[float]] = {}

    for _, row in history.iterrows():
        drv = str(row.get("Abbreviation", row.get("Driver", "")))
        tm = str(row.get("TeamName", row.get("Team", "")))
        pos = float(row.get("Position", 11.0))
        pts = float(row.get("Points", 0.0))
        status = str(row.get("Status", "Finished")).lower()
        is_dnf = int(not ("finished" in status or "lapped" in status or "+" in status))

        driver_finishes.setdefault(drv, []).append(pos)
        team_finishes.setdefault(tm, []).append(pos)
        team_pts_hist.setdefault(tm, []).append(pts)
        driver_dnfs.setdefault(drv, []).append(is_dnf)

    drv_ewma_map = {
        drv: ewma(vals, default=11.0, alpha=alpha)
        for drv, vals in driver_finishes.items()
    }
    tm_ewma_map = {
        tm: ewma(vals, default=11.0, alpha=alpha) for tm, vals in team_finishes.items()
    }
    tm_pts_map = {
        tm: ewma(vals, default=0.0, alpha=alpha) for tm, vals in team_pts_hist.items()
    }
    dnf_rate_map = {
        drv: float(np.mean(vals)) if vals else 0.05 for drv, vals in driver_dnfs.items()
    }

    result["driver_finish_ewma"] = (
        result[col_driver].map(drv_ewma_map).fillna(11.0).astype("float32")
    )
    result["team_finish_ewma"] = (
        result[col_team].map(tm_ewma_map).fillna(11.0).astype("float32")
    )
    result["team_points_ewma"] = (
        result[col_team].map(tm_pts_map).fillna(0.0).astype("float32")
    )
    result["driver_dnf_rate"] = (
        result[col_driver].map(dnf_rate_map).fillna(0.05).astype("float32")
    )

    return result
