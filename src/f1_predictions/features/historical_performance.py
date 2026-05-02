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
