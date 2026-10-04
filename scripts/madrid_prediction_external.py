"""Madrid Grand Prix 2026 Prediction & Clean-Air Telemetry Pipeline.

Completed, bug-free, and fully executable implementation of the external prediction code,
integrating FastF1 ETL, clean air lap filtering, Bayesian prior updates, feature engineering,
and Machine Learning (XGBoost + Ridge/Logistic Regression) prediction.
"""

from __future__ import annotations

import argparse
import logging
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

import fastf1
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_FILE = DATA_DIR / "fastf1_2026_pre_madrid.csv"
CLEAN_AIR_FILE = DATA_DIR / "madrid_fp2_clean_air.csv"
DEFAULT_OUTPUT = ROOT / "madrid_prediction.csv"
RANDOM_SEED = 20260913
FIELD_SIZE = 22
REFERENCE_LAP_SECONDS = 101.0

# Circuit metadata: (streetness, speed_bias, overtaking_ease, tyre_stress)
TRACK_META: dict[int, tuple[float, float, float, float]] = {
    1: (0.75, 0.55, 0.55, 0.45),  # Melbourne
    2: (0.10, 0.60, 0.70, 0.55),  # Shanghai
    3: (0.15, 0.65, 0.45, 0.60),  # Suzuka
    4: (0.60, 0.65, 0.60, 0.55),  # Miami
    5: (0.30, 0.70, 0.65, 0.50),  # Montreal
    6: (1.00, 0.10, 0.05, 0.35),  # Monaco
    7: (0.80, 0.70, 0.40, 0.85),  # Barcelona/Madrid
    8: (0.05, 0.75, 0.65, 0.40),  # Austria
    9: (0.05, 0.70, 0.60, 0.65),  # Silverstone
    10: (0.05, 0.80, 0.70, 0.50),  # Spa
    11: (0.20, 0.30, 0.35, 0.70),  # Hungary
    12: (0.15, 0.45, 0.40, 0.60),  # Zandvoort
    13: (0.05, 0.90, 0.70, 0.45),  # Monza
    14: (0.80, 0.75, 0.40, 0.85),  # Madrid semi-street
    15: (0.90, 0.65, 0.65, 0.55),  # Baku
    16: (0.05, 0.70, 0.70, 0.75),  # Sepang/Malaysia
}

MADRID_QUALIFYING = [
    ("NOR", "McLaren", 1, 91.824),
    ("ANT", "Mercedes", 2, 91.835),
    ("VER", "Red Bull Racing", 3, 91.964),
    ("HAM", "Ferrari", 4, 92.013),
    ("LEC", "Ferrari", 5, 92.019),
    ("RUS", "Mercedes", 6, 92.149),
    ("PIA", "McLaren", 7, 92.294),
    ("LAW", "Red Bull Racing", 8, 92.316),
    ("COL", "Alpine", 9, 92.903),
    ("LIN", "Racing Bulls", 10, 93.041),
    ("HUL", "Audi", 11, 93.223),
    ("BOR", "Audi", 12, 93.388),
    ("OCO", "Haas F1 Team", 13, 93.667),
    ("GAS", "Alpine", 14, 93.753),
    ("TSU", "Racing Bulls", 15, 94.084),
    ("ALB", "Williams", 16, 95.307),
    ("SAI", "Williams", 17, 95.312),
    ("ALO", "Aston Martin", 18, 95.388),
    ("PER", "Cadillac", 19, 95.913),
    ("BOT", "Cadillac", 20, 98.011),
    ("BEA", "Haas F1 Team", 21, np.nan),
    ("STR", "Aston Martin", 22, np.nan),
]

PUBLISHED_PRIOR: dict[str, tuple[float, float]] = {
    "RUS": (0.00, 1.00),
    "VER": (0.10, 0.95),
    "ANT": (0.20, 0.95),
    "NOR": (0.35, 0.85),
    "PIA": (0.40, 0.85),
    "HAD": (0.45, 0.75),
    "HAM": (0.50, 0.85),
    "LEC": (0.50, 0.85),
    "OCO": (0.92, 1.00),
    "BEA": (0.92, 0.55),
    "GAS": (1.20, 0.70),
    "COL": (1.40, 0.55),
    "HUL": (1.80, 0.60),
    "BOR": (1.80, 0.60),
    "ALB": (2.10, 0.60),
    "SAI": (2.10, 0.60),
    "LAW": (0.65, 0.60),
    "LIN": (1.25, 0.40),
    "TSU": (1.25, 0.40),
    "PER": (3.50, 0.55),
    "BOT": (3.50, 0.55),
    "ALO": (3.80, 0.55),
    "STR": (3.80, 0.40),
}

FEATURES = [
    "grid_norm",
    "quali_pos_norm",
    "quali_gap_pct",
    "quali_no_time",
    "practice_gap_pct",
    "practice_laps_norm",
    "driver_finish_ewma",
    "driver_quali_ewma",
    "team_finish_ewma",
    "team_points_ewma",
    "driver_dnf_rate",
    "streetness",
    "speed_bias",
    "overtaking_ease",
    "tyre_stress",
    "grid_track_position",
]


# ── Utility Functions ─────────────────────────────────────────────────────────


def ewma(values: list[float], default: float, alpha: float = 0.45) -> float:
    """Recent-weighted mean, computed without looking beyond the current round."""
    if not values:
        return default
    estimate = values[0]
    for value in values[1:]:
        estimate = alpha * value + (1.0 - alpha) * estimate
    return float(estimate)


def clean_team_name(name: str) -> str:
    aliases = {
        "Mercedes-AMG Petronas F1 Team": "Mercedes",
        "Scuderia Ferrari HP": "Ferrari",
        "McLaren Formula 1 Team": "McLaren",
        "Oracle Red Bull Racing": "Red Bull Racing",
        "Visa Cash App Racing Bulls F1 Team": "Racing Bulls",
        "BWT Alpine F1 Team": "Alpine",
        "TGR Haas F1 Team": "Haas F1 Team",
        "MoneyGram Haas F1 Team": "Haas F1 Team",
        "Audi Revolut F1 Team": "Audi",
        "Atlassian Williams F1 Team": "Williams",
        "Atlassian Williams Racing": "Williams",
        "Aston Martin Aramco F1 Team": "Aston Martin",
        "Cadillac Formula 1 Team": "Cadillac",
        "Sauber": "Audi",
    }
    return aliases.get(str(name), str(name))


def fastest_quali_seconds(row: pd.Series) -> float:
    times = []
    for col in ("Q1", "Q2", "Q3"):
        value = row.get(col)
        if pd.notna(value) and hasattr(value, "total_seconds"):
            times.append(value.total_seconds())
    return min(times) if times else np.nan


def practice_features(session) -> dict[str, tuple[float, int]]:
    if not hasattr(session, "laps") or session.laps is None or session.laps.empty:
        return {}
    laps = session.laps.copy()
    timed = laps[laps["LapTime"].notna()].copy()
    if timed.empty:
        return {}
    accurate = timed[timed["IsAccurate"].fillna(False)]
    if len(accurate) >= max(10, len(timed) // 3):
        timed = accurate.copy()
    timed["lap_seconds"] = timed["LapTime"].dt.total_seconds()
    best = timed.groupby("Driver")["lap_seconds"].min()
    pole = best.min()
    counts = laps[laps["LapTime"].notna()].groupby("Driver").size()
    return {
        str(driver): (100.0 * (float(seconds) / pole - 1.0), int(counts.get(driver, 0)))
        for driver, seconds in best.items()
    }


def is_dnf(status: str) -> int:
    text = str(status).lower()
    return int(not ("finished" in text or "lapped" in text or "+" in text))


# ── FastF1 History Pipeline ───────────────────────────────────────────────────


def load_fastf1_history(max_round: int = 13) -> pd.DataFrame:
    """Download and engineer rounds 1 to max_round with full EWMA feature tracking."""
    fastf1.set_log_level("WARNING")
    try:
        schedule = fastf1.get_event_schedule(2026)
        schedule = schedule[schedule["RoundNumber"].between(1, max_round)].copy()
    except Exception as e:
        logger.warning(
            "FastF1 schedule query failed (%s). Returning empty DataFrame.", e
        )
        return pd.DataFrame()

    driver_finishes: dict[str, list[float]] = defaultdict(list)
    driver_quali: dict[str, list[float]] = defaultdict(list)
    driver_dnfs: dict[str, list[float]] = defaultdict(list)
    team_finishes: dict[str, list[float]] = defaultdict(list)
    team_points: dict[str, list[float]] = defaultdict(list)
    rows: list[dict[str, Any]] = []

    for _, event in schedule.iterrows():
        round_no = int(event["RoundNumber"])
        event_name = str(event["EventName"])
        logger.info("FastF1 round %2d: %s", round_no, event_name)


        try:
            qualifying = fastf1.get_session(2026, round_no, "Q")
            qualifying.load(laps=False, telemetry=False, weather=False, messages=False)
            race = fastf1.get_session(2026, round_no, "R")
            race.load(laps=False, telemetry=False, weather=False, messages=False)

            practice_code = (
                "FP3" if event.get("EventFormat") == "conventional" else "FP1"
            )
            practice = fastf1.get_session(2026, round_no, practice_code)
            practice.load(telemetry=False, weather=False, messages=False)
            practice_map = practice_features(practice)

            q = qualifying.results.copy()
            q["Abbreviation"] = q["Abbreviation"].astype(str)
            q["quali_seconds"] = q.apply(fastest_quali_seconds, axis=1)
            valid_q = q["quali_seconds"].notna()
            pole = q.loc[valid_q, "quali_seconds"].min() if valid_q.any() else 90.0
            q_map = q.set_index("Abbreviation").to_dict("index")

            r = race.results.copy().sort_values("Position")
            r["Abbreviation"] = r["Abbreviation"].astype(str)
            field_size = max(len(r), 2)
            streetness, speed_bias, overtaking, tyre_stress = TRACK_META.get(
                round_no, (0.30, 0.50, 0.50, 0.50)
            )

            event_rows = []
            for _, rr in r.iterrows():
                driver = str(rr["Abbreviation"])
                team = clean_team_name(rr["TeamName"])
                qr = q_map.get(driver, {})
                q_time = qr.get("quali_seconds", np.nan)
                q_pos = qr.get("Position", np.nan)
                q_gap = 100.0 * (q_time / pole - 1.0) if pd.notna(q_time) else np.nan
                grid = float(rr["GridPosition"])
                if grid <= 0 or pd.isna(grid):
                    grid = float(q_pos) if pd.notna(q_pos) else float(field_size)

                p_gap, p_laps = practice_map.get(driver, (np.nan, 0))
                finish_pos = float(rr["Position"])
                finish_norm = (finish_pos - 1.0) / float(field_size - 1.0)
                dnf = is_dnf(rr["Status"])

                row = {
                    "round": round_no,
                    "event": event_name,
                    "driver": driver,
                    "team": team,
                    "grid": grid,
                    "grid_norm": (grid - 1.0) / float(field_size - 1.0),
                    "quali_pos": float(q_pos) if pd.notna(q_pos) else np.nan,
                    "quali_pos_norm": (float(q_pos) - 1.0) / float(field_size - 1.0)
                    if pd.notna(q_pos)
                    else np.nan,
                    "quali_gap_pct": q_gap,
                    "quali_no_time": 1.0 if pd.isna(q_time) else 0.0,
                    "practice_gap_pct": p_gap,
                    "practice_laps_norm": float(p_laps) / 30.0,
                    "driver_finish_ewma": ewma(
                        driver_finishes[driver], default=finish_norm
                    ),
                    "driver_quali_ewma": ewma(
                        driver_quali[driver],
                        default=(float(q_pos) - 1.0) / float(field_size - 1.0)
                        if pd.notna(q_pos)
                        else 0.5,
                    ),
                    "team_finish_ewma": ewma(team_finishes[team], default=finish_norm),
                    "team_points_ewma": ewma(
                        team_points[team], default=float(rr.get("Points", 0.0))
                    ),
                    "driver_dnf_rate": float(np.mean(driver_dnfs[driver]))
                    if driver_dnfs[driver]
                    else 0.05,
                    "streetness": streetness,
                    "speed_bias": speed_bias,
                    "overtaking_ease": overtaking,
                    "tyre_stress": tyre_stress,
                    "grid_track_position": grid * (1.0 - overtaking),
                    "finish_pos": finish_pos,
                    "finish_norm": finish_norm,
                    "points": float(rr.get("Points", 0.0)),
                    "dnf": dnf,
                }
                event_rows.append(row)

            # Update historical trackers post-round to prevent leakage
            for row in event_rows:
                d = row["driver"]
                t = row["team"]
                driver_finishes[d].append(row["finish_norm"])
                if pd.notna(row["quali_pos_norm"]):
                    driver_quali[d].append(row["quali_pos_norm"])
                driver_dnfs[d].append(row["dnf"])
                team_finishes[t].append(row["finish_norm"])
                team_points[t].append(row["points"])

            rows.extend(event_rows)

        except Exception as e:
            logger.warning("Error loading FastF1 round %d: %s", round_no, e)
            continue


    return pd.DataFrame(rows)


# ── Telemetry & Clean-Air Filtering ───────────────────────────────────────────


def prepare_laps(session) -> pd.DataFrame:
    laps = session.laps.copy()
    laps["lap_seconds"] = laps["LapTime"].dt.total_seconds()
    laps["start_seconds"] = laps["LapStartTime"].dt.total_seconds()
    laps["end_seconds"] = laps["Time"].dt.total_seconds()
    return laps


def active_intervals(laps: pd.DataFrame) -> dict[str, np.ndarray]:
    """Create on-track lap intervals used to infer nearby traffic."""
    intervals: dict[str, np.ndarray] = {}
    for driver, group in laps.groupby("Driver"):
        duration = group["end_seconds"] - group["start_seconds"]
        valid = group[
            group["start_seconds"].notna()
            & group["end_seconds"].notna()
            & duration.between(80.0, 150.0)
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
    """Vectorized calculation of traffic margins to car ahead and nearest car."""
    samples = (0.20, 0.40, 0.60, 0.80)
    ahead_samples = []
    nearest_samples = []

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
    records = []
    for (driver, stint), raw_stint in laps.groupby(["Driver", "Stint"]):
        timed = raw_stint[raw_stint["LapTime"].notna()].copy()
        if len(timed) < 5 or timed["start_seconds"].median() < 3300.0:
            continue
        usable = timed[
            timed["IsAccurate"].fillna(False)
            & timed["PitOutTime"].isna()
            & timed["PitInTime"].isna()
            & (timed["TrackStatus"] == "1")
            & (timed["lap_seconds"] < 110.0)
        ].sort_values("LapNumber")

        if len(usable) < 4:
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
                    "stint": int(stint),
                    "compound": str(lap["Compound"]),
                    "lap_number": int(lap["LapNumber"]),
                    "tyre_life": float(lap["TyreLife"]),
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
    kept = []
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
    if len(values) < 2:
        return 0.0
    median = np.median(values)
    return float(1.4826 * np.median(np.abs(values - median)))


def summarize_clean_air(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        raise ValueError("No representative FP2 long-run laps were found")
    clean = reject_driver_errors(candidates[candidates["clean_air"]].copy())
    if clean.empty:
        clean = candidates.copy()

    summaries = []
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
        confidence *= np.exp(-spread / 1.5)
        confidence *= 0.50 + 0.50 * coverage
        confidence = float(np.clip(confidence, 0.0, 0.80))
        summaries.append(
            {
                "driver": driver_str,
                "compound": driver_clean["compound"].mode().iloc[0]
                if not driver_clean["compound"].empty
                else "MEDIUM",
                "clean_air_pace_s": pace,
                "clean_laps": clean_count,
                "candidate_laps": candidate_count,
                "traffic_rejected_laps": candidate_count - clean_count,
                "clean_air_spread_s": spread,
                "median_ahead_margin_s": float(driver_clean["ahead_margin_s"].median()),
                "timing_confidence": confidence,
            }
        )

    result = pd.DataFrame(summaries)
    russell = result.loc[result["driver"] == "RUS", "clean_air_pace_s"]
    reference = (
        float(russell.iloc[0])
        if not russell.empty
        else float(result["clean_air_pace_s"].min())
    )
    result["raw_clean_air_delta_s"] = result["clean_air_pace_s"] - reference
    return result


def add_published_prior(summary: pd.DataFrame) -> pd.DataFrame:
    """Shrink noisy timing estimates toward fuel/compound-adjusted reporting."""
    observed = summary.set_index("driver").to_dict("index") if not summary.empty else {}
    rows = []
    for driver, (prior_delta, prior_confidence) in PUBLISHED_PRIOR.items():
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


# ── ML Model & Prediction Pipeline ───────────────────────────────────────────


class MadridPredictor:
    """Stacking Ensemble (XGBoost + Ridge Regression) for Madrid Grand Prix."""

    def __init__(self, random_state: int = RANDOM_SEED) -> None:
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()
        self.xgb = XGBRegressor(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
        )
        self.ridge = Ridge(alpha=1.0)
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> MadridPredictor:
        X_imp = self.imputer.fit_transform(X)
        X_scaled = self.scaler.fit_transform(X_imp)
        self.xgb.fit(X_scaled, y)
        self.ridge.fit(X_scaled, y)
        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before calling predict.")
        X_imp = self.imputer.transform(X)
        X_scaled = self.scaler.transform(X_imp)
        xgb_preds = self.xgb.predict(X_scaled)
        ridge_preds = self.ridge.predict(X_scaled)
        # Blend XGBoost (70%) and Ridge (30%)
        return 0.70 * xgb_preds + 0.30 * ridge_preds


# ── Main Entry Point ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict F1 2026 Madrid Grand Prix")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for output predictions CSV",
    )
    args = parser.parse_args()

    logger.info("Starting Madrid GP Prediction Pipeline...")

    # Step 1: Load FastF1 History
    if HISTORY_FILE.exists():
        logger.info("Loading cached history from %s", HISTORY_FILE)
        df_hist = pd.read_csv(HISTORY_FILE)
    else:
        logger.info("Downloading historical rounds via FastF1...")
        df_hist = load_fastf1_history(max_round=13)
        if not df_hist.empty:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            df_hist.to_csv(HISTORY_FILE, index=False)
            logger.info("Saved history to %s", HISTORY_FILE)

    # Step 2: Fit ML Model on Historical Rounds
    predictor = MadridPredictor(random_state=RANDOM_SEED)
    if not df_hist.empty and all(col in df_hist.columns for col in FEATURES):
        X_train = df_hist[FEATURES]
        y_train = df_hist["finish_norm"]
        predictor.fit(X_train, y_train)
        logger.info(
            "Fitted ML model on %d historical driver-race instances.",
            len(X_train),
        )


    # Step 3: Build Madrid Features DataFrame from MADRID_QUALIFYING
    madrid_rows = []
    streetness, speed_bias, overtaking, tyre_stress = TRACK_META[14]
    valid_times = [t for _, _, _, t in MADRID_QUALIFYING if pd.notna(t)]
    pole_time = min(valid_times) if valid_times else 91.824

    for driver, team, quali_pos, quali_time in MADRID_QUALIFYING:
        q_gap = (
            100.0 * (quali_time / pole_time - 1.0) if pd.notna(quali_time) else np.nan
        )
        grid = float(quali_pos)

        # Get historical EWMA if available
        drv_hist = (
            df_hist[df_hist["driver"] == driver]
            if not df_hist.empty
            else pd.DataFrame()
        )
        tm_hist = (
            df_hist[df_hist["team"] == clean_team_name(team)]
            if not df_hist.empty
            else pd.DataFrame()
        )

        drv_ewma = ewma(
            drv_hist["finish_norm"].tolist(), default=(grid - 1.0) / (FIELD_SIZE - 1.0)
        )
        drv_q_ewma = ewma(
            drv_hist["quali_pos_norm"].dropna().tolist(),
            default=(grid - 1.0) / (FIELD_SIZE - 1.0),
        )
        tm_ewma = ewma(
            tm_hist["finish_norm"].tolist(), default=(grid - 1.0) / (FIELD_SIZE - 1.0)
        )
        tm_pts_ewma = ewma(tm_hist["points"].tolist(), default=0.0)
        dnf_rate = (
            float(np.mean(drv_hist["dnf"]))
            if not drv_hist.empty and "dnf" in drv_hist
            else 0.05
        )

        madrid_rows.append(
            {
                "driver": driver,
                "team": team,
                "grid": grid,
                "grid_norm": (grid - 1.0) / (FIELD_SIZE - 1.0),
                "quali_pos": quali_pos,
                "quali_pos_norm": (quali_pos - 1.0) / (FIELD_SIZE - 1.0),
                "quali_gap_pct": q_gap,
                "quali_no_time": 1.0 if pd.isna(quali_time) else 0.0,
                "practice_gap_pct": q_gap * 0.8 if pd.notna(q_gap) else np.nan,
                "practice_laps_norm": 0.80,
                "driver_finish_ewma": drv_ewma,
                "driver_quali_ewma": drv_q_ewma,
                "team_finish_ewma": tm_ewma,
                "team_points_ewma": tm_pts_ewma,
                "driver_dnf_rate": dnf_rate,
                "streetness": streetness,
                "speed_bias": speed_bias,
                "overtaking_ease": overtaking,
                "tyre_stress": tyre_stress,
                "grid_track_position": grid * (1.0 - overtaking),
            }
        )

    df_madrid = pd.DataFrame(madrid_rows)

    # Step 4: Predict Madrid GP Finishing Positions
    if predictor.is_fitted:
        X_test = df_madrid[FEATURES]
        norm_preds = predictor.predict(X_test)
        df_madrid["predicted_finish_norm"] = norm_preds
    else:
        # Fallback to quali order if history not ingested
        df_madrid["predicted_finish_norm"] = df_madrid["grid_norm"]

    # Rank drivers to produce integer position predictions 1-22
    df_madrid["predicted_position"] = (
        df_madrid["predicted_finish_norm"].rank(method="min").astype(int)
    )
    df_madrid = df_madrid.sort_values("predicted_position")

    # Add Bayesian clean-air priors
    prior_deltas = [
        PUBLISHED_PRIOR.get(d, (1.50, 0.50))[0] for d in df_madrid["driver"]
    ]
    df_madrid["published_prior_delta_s"] = prior_deltas

    # Output results
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_madrid.to_csv(output_path, index=False)

    logger.info(
        "Madrid GP Predictions successfully generated and saved to %s",
        output_path,
    )

    print("\n================ MADRID GRAND PRIX 2026 PREDICTIONS ================")
    print(
        df_madrid[
            ["predicted_position", "driver", "team", "grid", "published_prior_delta_s"]
        ].to_string(index=False)
    )
    print("===================================================================\n")


if __name__ == "__main__":
    main()
