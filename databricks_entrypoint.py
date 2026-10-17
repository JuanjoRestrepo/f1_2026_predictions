"""Databricks Job Entry Point for the F1 2026 Predictions Pipeline.

This script is the exclusive entry point for Databricks Lakeflow Jobs.
It is NOT intended for local use — use `main.py` locally instead.

Design rationale:
    - `main.py` is a local orchestrator that calls `uv run scripts/...` via
      subprocess and expects `--round`/`--event` positional args. That interface
      is incompatible with Databricks job parameters.
    - This file exposes a clean `--run-mode {train,notify}` + `--season` CLI
      that maps directly to Databricks job task parameters in `resources/jobs.yml`.
    - Separating concerns prevents `main.py` from growing Databricks-specific
      branching logic that breaks local execution.

Usage (Databricks job):
    python databricks_entrypoint.py --run-mode train --season 2026
    python databricks_entrypoint.py --run-mode notify --season 2026

Deployed via DABs:
    resources/jobs.yml → spark_python_task.python_file: ../databricks_entrypoint.py
"""

from __future__ import annotations

import argparse
import pathlib
import sys

# ---------------------------------------------------------------------------
# Ensure src/ is on sys.path for Databricks driver-mode execution.
# The Databricks executor places the bundle root in the working directory,
# so PROJECT_ROOT / src resolves correctly regardless of CWD.
# ---------------------------------------------------------------------------
try:
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
except NameError:
    # __file__ is not defined when exec'd in an IPyKernel context
    PROJECT_ROOT = pathlib.Path.cwd()

SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ---------------------------------------------------------------------------
# Imports — deferred until after sys.path is patched
# ---------------------------------------------------------------------------
from f1_predictions.databricks.mlflow_utils import (  # noqa: E402
    register_champion_model,
    track_experiment,
)
from f1_predictions.utils.logging_setup import (  # noqa: E402
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)


import os  # noqa: E402

USER_EMAIL = os.environ.get("DATABRICKS_USER", "restrepojuanjo@gmail.com")
EXPERIMENT_NAME = f"/Users/{USER_EMAIL}/f1_2026_race_pace"
MODEL_NAME = "xgb_race_pace_regressor"

CATALOG = os.environ.get("F1_CATALOG", "main")
SCHEMA = os.environ.get("F1_SCHEMA", "race_pace")


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------


def run_train(season: int, catalog: str = CATALOG, schema: str = SCHEMA) -> None:
    """Train the XGBoost pace regressor and register @champion in Unity Catalog.

    Pipeline:
        1. Read DLT-materialized Gold Delta table in Unity Catalog.
        2. Train XGBoost pace regressor and cross-validate.
        3. Track training run in MLflow experiment with signature.
        4. Promote registered model version to @champion alias in Unity Catalog.

    Args:
        season: F1 season year (e.g. 2026) used to tag the MLflow run.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
    """
    logger.info("=" * 60)
    logger.info("DATABRICKS TRAIN MODE — Season %d (%s.%s)", season, catalog, schema)
    logger.info("=" * 60)

    # ── Step 1: Read Gold feature set ───────────────────────────────────────
    gold_df = None
    target_tbl = f"{catalog}.{schema}.driver_features_gold"
    try:
        from pyspark.sql import SparkSession  # type: ignore[import-untyped]

        spark = SparkSession.builder.getOrCreate()
        logger.info(
            "Attempting to load Gold features from Unity Catalog table '%s'…",
            target_tbl,
        )
        if spark.catalog.tableExists(target_tbl) or spark.catalog.tableExists(
            "driver_features_gold"
        ):
            tbl = (
                target_tbl
                if spark.catalog.tableExists(target_tbl)
                else "driver_features_gold"
            )
            gold_spark_df = spark.table(tbl)
            if gold_spark_df.count() > 0:
                gold_df = gold_spark_df.toPandas()
                logger.info(
                    "Successfully loaded %d real Gold feature rows from table '%s'",
                    len(gold_df),
                    tbl,
                )
    except Exception:
        logger.exception("Spark table lookup failed for '%s'", target_tbl)

    if gold_df is None or len(gold_df) == 0:
        msg = (
            f"Gold feature table '{target_tbl}' was not found in Unity Catalog. "
            f"Ensure the DLT medallion pipeline has completed "
            f"successfully before running the train task."
        )
        raise RuntimeError(msg)

    # ── Step 2: Train XGBoost pace regressor ────────────────────────────────
    from sklearn.model_selection import cross_val_score  # type: ignore[import-untyped]
    from xgboost import XGBRegressor  # type: ignore[import-untyped]

    feature_cols = [
        "total_laps",
        "mean_pace_seconds",
        "pace_std_seconds",
        "tyre_degradation_slope",
    ]
    target_col = "fastest_lap_seconds"

    available_features = [c for c in feature_cols if c in gold_df.columns]
    X = gold_df[available_features].fillna(0.0)  # noqa: N806
    y = gold_df[target_col]

    params: dict[str, object] = {
        "n_estimators": 200,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "random_state": 42,
        "season": season,
    }
    model = XGBRegressor(
        n_estimators=int(params["n_estimators"]),
        max_depth=int(params["max_depth"]),
        learning_rate=float(params["learning_rate"]),
        subsample=float(params["subsample"]),
        random_state=int(params["random_state"]),
        tree_method="hist",
    )

    # Cross-validate to get reliable RMSE estimate
    cv_scores = cross_val_score(
        model, X, y, cv=3, scoring="neg_root_mean_squared_error"
    )

    rmse = float(-cv_scores.mean())
    rmse_std = float((-cv_scores).std())  # fold-to-fold RMSE dispersion

    model.fit(X, y)
    logger.info("XGBoost model trained — CV RMSE: %.4f (±%.4f)", rmse, rmse_std)

    from mlflow.models import infer_signature  # type: ignore[import-untyped]

    signature = infer_signature(X, model.predict(X))
    uc_model_name = f"{catalog}.{schema}.{MODEL_NAME}"
    summary = track_experiment(
        experiment_name=EXPERIMENT_NAME,
        params={str(k): str(v) for k, v in params.items()},
        metrics={"rmse": rmse, "cv_std": rmse_std},
        run_name=f"xgb_pace_{season}",
        model=model,
        registered_model_name=uc_model_name,
        signature=signature,
    )
    logger.info("MLflow run tracked: %s", summary.get("run_id"))

    # ── Step 4: Register @champion alias ────────────────────────────────────
    champion_path = register_champion_model(
        model_name=MODEL_NAME,
        catalog=catalog,
        schema=schema,
        alias="champion",
    )
    logger.info("Champion model registered at: %s", champion_path)
    logger.info("=" * 60)
    logger.info("TRAIN COMPLETE — Season %d", season)
    logger.info("=" * 60)


def run_notify(
    season: int,
    catalog: str = CATALOG,
    schema: str = SCHEMA,
    round_number: int | None = None,
) -> None:
    """Dispatch race verdict notifications (Gmail + Discord) using real outputs.

    Computes accuracy against actuals if post-race, or previews predictions
    if pre-race. Dispatches to configured channels.

    Args:
        season: F1 season year for the notification context.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        round_number: Optional explicit round number to report.
    """
    logger.info("=" * 60)
    logger.info("DATABRICKS NOTIFY MODE — Season %d (%s.%s)", season, catalog, schema)
    logger.info("=" * 60)

    try:
        import pandas as pd

        from f1_predictions.evaluation.post_race_verdict import (
            RaceVerdict,
            compute_verdict,
            load_actuals,
            load_predictions,
        )
        from f1_predictions.utils.config import get_settings
        from f1_predictions.utils.email_builder import (
            build_email_html,
            build_subject,
        )
        from f1_predictions.utils.notifications import (
            DiscordWebhookChannel,
            GmailSMTPChannel,
            NotificationDispatcher,
            RaceBriefingPayload,
        )
        from f1_predictions.utils.race_detector import (
            detect_last_race,
            detect_upcoming_race,
        )

        settings = get_settings()

        # ── Step 1: Detect race to report ────────────────────────────────────
        round_num = round_number
        event_name: str | None = None
        is_post_race = False

        if round_num is None:
            # Isolate network-backed detection: a FastF1 hiccup must not abort
            # the whole notification — the local-reports fallback below still
            # holds valid predictions to report on.
            try:
                last_race = detect_last_race(season=season, days_back=7)
            except Exception as exc:
                logger.warning(
                    "Live calendar detection failed (%s); using local reports.", exc
                )
                last_race = None

            if last_race is not None:
                round_num = int(last_race["round"])
                event_name = str(last_race["gp_name"])
                is_post_race = True
            else:
                try:
                    upcoming = detect_upcoming_race(season=season, days_ahead=4)
                except Exception as exc:
                    logger.warning(
                        "Upcoming-race detection failed (%s); using local reports.",
                        exc,
                    )
                    upcoming = None
                if upcoming is not None:
                    round_num = int(upcoming["round"])
                    event_name = str(upcoming["gp_name"])
                    is_post_race = False

        def _round_has_predictions(gp: str | None) -> bool:
            if gp is None:
                return False
            pred = (
                PROJECT_ROOT
                / "reports"
                / str(season)
                / gp.replace(" ", "_")
                / "results"
                / "predictions.csv"
            )
            return pred.exists()

        def _latest_available_round() -> tuple[int, str] | None:
            """Newest round with a local predictions.csv, or None."""
            reports_season_dir = PROJECT_ROOT / "reports" / str(season)
            if not reports_season_dir.exists():
                return None
            rounds: list[tuple[int, str]] = []
            for p in reports_season_dir.iterdir():
                pred = p / "results" / "predictions.csv"
                if not (p.is_dir() and pred.exists()):
                    continue
                try:
                    head = pd.read_csv(pred, nrows=1)
                    rnd = (
                        int(head["RoundNumber"].iloc[0]) if "RoundNumber" in head else 1
                    )
                    gp = (
                        str(head["EventName"].iloc[0])
                        if "EventName" in head
                        else p.name.replace("_", " ")
                    )
                    rounds.append((rnd, gp))
                except Exception as exc:
                    logger.debug("Could not read predictions in %s: %s", p, exc)
            if not rounds:
                return None
            rounds.sort(key=lambda x: x[0])
            return rounds[-1]

        # Fallback (auto mode only): the live calendar may point at a round for
        # which we have produced no artifacts yet (e.g. a just-finished race the
        # pipeline has not processed). In that case report on the newest round we
        # can actually evidence, rather than notifying about an empty round.
        if round_number is None and not _round_has_predictions(event_name):
            latest = _latest_available_round()
            if latest is not None:
                prior_round, prior_event = round_num, event_name
                round_num, event_name = latest
                is_post_race = True
                if prior_round is not None:
                    logger.info(
                        "Detected R%s (%s) has no local predictions; using latest "
                        "available R%d (%s).",
                        prior_round,
                        prior_event,
                        round_num,
                        event_name,
                    )

        if round_num is None or event_name is None:
            logger.warning(
                "No race found in reports for season %d. Notification skipped.",
                season,
            )
            return

        logger.info(
            "Resolved notification target: Round %d — %s (mode: %s)",
            round_num,
            event_name,
            "post-race" if is_post_race else "pre-race",
        )

        # ── Step 2: Compute verdict (real post-race, preview otherwise) ──────
        safe_event = event_name.replace(" ", "_")
        results_dir = PROJECT_ROOT / "reports" / str(season) / safe_event / "results"
        predictions_path = results_dir / "predictions.csv"

        def _preview_verdict(rnd: int, gp: str) -> RaceVerdict:
            """Pre-race / degraded verdict that carries no fabricated accuracy.

            Uses an explicit ``preview`` status so downstream rendering never
            presents placeholder zeroes as a measured "excellent" result.
            """
            return RaceVerdict(
                round=rnd,
                gp_name=gp,
                mae_lap_time_s=0.0,
                mape_pct=0.0,
                winner_correct=False,
                podium_accuracy_pct=0.0,
                top10_accuracy_pct=0.0,
                key_misses=[],
                status="preview",
            )

        verdict: RaceVerdict
        if is_post_race:
            try:
                actuals = load_actuals(season, round_num)
                predictions = load_predictions(predictions_path)
                verdict = compute_verdict(predictions, actuals, round_num, event_name)
            except Exception as actuals_err:
                # Never fabricate accuracy: if the ground-truth verdict cannot
                # be computed, degrade to an honest prediction preview rather
                # than emailing a fake perfect score.
                logger.warning(
                    "Could not compute a real verdict for %d R%d (%s); "
                    "degrading to prediction preview.",
                    season,
                    round_num,
                    actuals_err,
                )
                is_post_race = False
                verdict = _preview_verdict(round_num, event_name)
        else:
            verdict = _preview_verdict(round_num, event_name)

        # ── Step 3: Load AI narrative report (match the effective mode) ──────
        summaries_dir = PROJECT_ROOT / "reports" / str(season) / "summaries"
        if is_post_race:
            report_candidates = [
                results_dir / f"report_round_{round_num}.md",
                results_dir / f"report_round_{round_num:02d}.md",
                summaries_dir / f"report_round_{round_num}.md",
                summaries_dir / f"report_round_{round_num:02d}.md",
            ]
        else:
            report_candidates = [
                results_dir / f"predicted_report_round_{round_num}.md",
                results_dir / f"predicted_report_round_{round_num:02d}.md",
                summaries_dir / f"predicted_report_round_{round_num}.md",
                summaries_dir / f"predicted_report_round_{round_num:02d}.md",
            ]
        ai_narrative: str | None = None
        for cand in report_candidates:
            if cand.exists():
                ai_narrative = cand.read_text(encoding="utf-8")
                break

        # ── Step 4: Configure channels and dispatch ──────────────────────────
        gmail_user = settings.gmail_user
        gmail_pass = settings.gmail_app_password
        discord_url = settings.discord_webhook_url

        try:
            from pyspark.dbutils import DBUtils  # type: ignore[import-untyped]
            from pyspark.sql import SparkSession

            spark = SparkSession.builder.getOrCreate()
            dbutils = DBUtils(spark)
            gmail_user = gmail_user or dbutils.secrets.get(
                scope="f1_secrets", key="F1_GMAIL_USER"
            )
            gmail_pass = gmail_pass or dbutils.secrets.get(
                scope="f1_secrets", key="F1_GMAIL_APP_PASSWORD"
            )
            discord_url = discord_url or dbutils.secrets.get(
                scope="f1_secrets", key="F1_DISCORD_WEBHOOK_URL"
            )
        except Exception:
            logger.debug(
                "Databricks secrets lookup skipped; using env var configuration."
            )

        channels = []
        if gmail_user and gmail_pass:
            channels.append(
                GmailSMTPChannel(
                    gmail_user=gmail_user,
                    app_password=gmail_pass,
                    recipient_email=settings.recipient_email or gmail_user,
                )
            )
        if discord_url:
            channels.append(DiscordWebhookChannel(webhook_url=discord_url))

        if channels:
            dispatcher = NotificationDispatcher(channels=channels)
            subj_prefix = "" if is_post_race else "🚀 PREDICTION PREVIEW: "
            subject = subj_prefix + build_subject(verdict)
            html_body = build_email_html(verdict=verdict, ai_narrative=ai_narrative)
            payload = RaceBriefingPayload(
                verdict=verdict,
                subject=subject,
                html_body=html_body,
            )
            results = dispatcher.dispatch(payload)
            logger.info("Race verdict notifications dispatched: %s", results)
        else:
            logger.info(
                "Race verdict summary logged for Round %d (%s). "
                "Add 'f1_secrets' or env vars to deliver notifications.",
                round_num,
                event_name,
            )
    except Exception:
        logger.warning(
            "Notification dispatch skipped — configuration or secrets unavailable.",
            exc_info=True,
        )

    logger.info("=" * 60)
    logger.info("NOTIFY COMPLETE — Season %d", season)
    logger.info("=" * 60)


def is_race_window_active(season: int) -> bool:
    """Determine if today is within a Race Weekend (Fri-Sun) or post-race Monday."""
    try:
        from f1_predictions.utils.race_detector import (
            detect_last_race,
            detect_upcoming_race,
        )

        last_race = detect_last_race(season=season, days_back=2)
        upcoming_race = detect_upcoming_race(season=season, days_ahead=3)
    except Exception as exc:
        logger.warning(
            "Could not fetch FastF1 schedule (%s). Executing pipeline by default.",
            exc,
        )
        return True

    return last_race is not None or upcoming_race is not None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate run mode."""
    configure_root_pipeline_logger(level="INFO")

    parser = argparse.ArgumentParser(
        prog="databricks_entrypoint",
        description=(
            "Databricks Lakeflow Job entry point for the F1 2026 Predictions Pipeline. "
            "Dispatches to train or notify mode based on --run-mode."
        ),
    )
    parser.add_argument(
        "--run-mode",
        required=True,
        choices=["train", "notify"],
        help="Execution mode: 'train' trains XGBoost and registers @champion; "
        "'notify' dispatches race verdict to Gmail and Discord.",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="F1 season year (default: 2026).",
    )
    parser.add_argument(
        "--catalog",
        default=os.environ.get("F1_CATALOG", "main"),
        help="Unity Catalog catalog name.",
    )
    parser.add_argument(
        "--schema",
        default=os.environ.get("F1_SCHEMA", "race_pace"),
        help="Unity Catalog schema name.",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        help="F1 round number override for notifications.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass race weekend gate and force execution.",
    )

    args = parser.parse_args()
    logger.info(
        "Databricks entrypoint: mode=%s, season=%d, catalog=%s, schema=%s, force=%s",
        args.run_mode,
        args.season,
        args.catalog,
        args.schema,
        args.force,
    )

    if not args.force and not is_race_window_active(args.season):
        logger.info(
            "Non-race day detected (season %d). Skipping execution.",
            args.season,
        )
        return

    if args.run_mode == "train":
        run_train(season=args.season, catalog=args.catalog, schema=args.schema)
    elif args.run_mode == "notify":
        run_notify(
            season=args.season,
            catalog=args.catalog,
            schema=args.schema,
            round_number=args.round,
        )


if __name__ == "__main__":
    main()
