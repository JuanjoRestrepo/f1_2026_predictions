"""Databricks Job Entry Point for the F1 2026 Predictions Pipeline.

This script is the exclusive entry point for Databricks Lakeflow Jobs.
It is NOT intended for local use — use `main.py` locally instead.

Design rationale:
    - `main.py` is a local orchestrator that calls `uv run scripts/...` via
      subprocess and expects `--round`/`--event` positional args. That interface
      is incompatible with Databricks job parameters.
    - This file exposes a clean `--run-mode {ingest,train,predict,notify,export}`
      + `--season` CLI
      that maps directly to Databricks job task parameters in `resources/jobs.yml`.
    - Separating concerns prevents `main.py` from growing Databricks-specific
      branching logic that breaks local execution.

Usage (Databricks job):
    python databricks_entrypoint.py --run-mode ingest --season 2026
    python databricks_entrypoint.py --run-mode train  --season 2026
    python databricks_entrypoint.py --run-mode train  --season 2026 \
        --training-schema lap
    python databricks_entrypoint.py --run-mode predict --season 2026 \
        --training-schema lap
    python databricks_entrypoint.py --run-mode notify --season 2026
    python databricks_entrypoint.py --run-mode export --season 2026

Deployed via DABs:
    resources/jobs.yml → spark_python_task.python_file: ../databricks_entrypoint.py
"""

from __future__ import annotations

import argparse
import os
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
    get_champion_metric,
    register_champion_model,
    should_promote,
    track_experiment,
)
from f1_predictions.features.contract import (  # noqa: E402
    TRAINING_SCHEMAS,
    resolve_training_schema,
)
from f1_predictions.features.training_data import (  # noqa: E402
    build_prediction_frame,
    prepare_feature_frame,
    prepare_training_data,
)
from f1_predictions.utils.logging_setup import (  # noqa: E402
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)


USER_EMAIL = os.environ.get("DATABRICKS_USER", "restrepojuanjo@gmail.com")
EXPERIMENT_NAME = f"/Users/{USER_EMAIL}/f1_2026_race_pace"
TRAINING_SCHEMA_CHOICES = tuple(sorted(TRAINING_SCHEMAS))

CATALOG = os.environ.get("F1_CATALOG", "main")
SCHEMA = os.environ.get("F1_SCHEMA", "race_pace")


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------


def run_train(
    season: int,
    catalog: str = CATALOG,
    schema: str = SCHEMA,
    training_schema: str = "aggregate",
) -> None:
    """Train an XGBoost pace regressor and register @champion in Unity Catalog.

    Two opt-in lanes share one code path but never share a registered model:

    * ``aggregate`` (default) — the historical per-driver Gold table targeting
      ``fastest_lap_seconds``. Its 3-fold CV and ``fillna(0.0)`` behaviour are
      unchanged.
    * ``lap`` — the Task 21.3 per-lap table targeting ``LapTime_s``. It uses
      event-grouped CV, leaves NaN rolling features intact and registers under
      ``xgb_lap_pace_regressor`` so its RMSE is never compared with the
      aggregate model's RMSE.

    Args:
        season: F1 season year used to tag the MLflow run.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        training_schema: ``aggregate`` or ``lap``.
    """
    spec = resolve_training_schema(training_schema)
    logger.info("=" * 60)
    logger.info(
        "DATABRICKS TRAIN MODE — Season %d (%s.%s, schema=%s)",
        season,
        catalog,
        schema,
        spec.name,
    )
    logger.info("=" * 60)

    # ── Step 1: Read the schema's Gold feature set ─────────────────────────
    gold_df = None
    target_tbl = f"{catalog}.{schema}.{spec.table}"
    try:
        from pyspark.sql import SparkSession  # type: ignore[import-untyped]

        spark = SparkSession.builder.getOrCreate()
        logger.info(
            "Attempting to load Gold features from Unity Catalog table '%s'…",
            target_tbl,
        )
        if spark.catalog.tableExists(target_tbl) or spark.catalog.tableExists(
            spec.table
        ):
            tbl = target_tbl if spark.catalog.tableExists(target_tbl) else spec.table
            gold_spark_df = spark.table(tbl)
            if gold_spark_df.count() > 0:
                gold_df = gold_spark_df.toPandas()
                logger.info(
                    "Successfully loaded %d Gold rows from table '%s'",
                    len(gold_df),
                    tbl,
                )
    except Exception:
        logger.exception("Spark table lookup failed for '%s'", target_tbl)

    if gold_df is None or len(gold_df) == 0:
        msg = (
            f"Gold table '{target_tbl}' was not found or returned no rows. "
            "Ensure the DLT medallion pipeline has completed successfully "
            "before running the train task."
        )
        raise RuntimeError(msg)

    # ── Step 2: Validate the shared contract and build the matrix ──────────
    training_data = prepare_training_data(gold_df, spec)
    X = training_data.X.reset_index(drop=True)  # noqa: N806
    y = training_data.y.reset_index(drop=True)
    groups = (
        training_data.groups.reset_index(drop=True)
        if training_data.groups is not None
        else None
    )
    logger.info(
        "Contract v%s accepted: %d rows x %d features (%d target row(s) dropped).",
        spec.contract_version or "legacy",
        len(X),
        len(spec.features),
        training_data.dropped_target_rows,
    )

    from sklearn.model_selection import (  # type: ignore[import-untyped]
        GroupKFold,
        cross_val_score,
    )
    from xgboost import XGBRegressor  # type: ignore[import-untyped]

    params: dict[str, object] = {
        "n_estimators": 200,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "random_state": 42,
        "season": season,
        "training_schema": spec.name,
        "contract_version": spec.contract_version or 0,
        "feature_count": len(spec.features),
    }
    model = XGBRegressor(
        n_estimators=int(params["n_estimators"]),
        max_depth=int(params["max_depth"]),
        learning_rate=float(params["learning_rate"]),
        subsample=float(params["subsample"]),
        random_state=int(params["random_state"]),
        tree_method="hist",
    )

    # Event-grouped CV for lap rows: laps from the same race are not independent.
    if groups is not None:
        n_groups = int(groups.nunique())
        if n_groups < 2:
            msg = (
                f"Table '{target_tbl}' contains {n_groups} event group(s). "
                "Event-grouped CV needs at least two races before it can "
                "produce an honest out-of-event estimate."
            )
            raise RuntimeError(msg)
        n_splits = min(5, n_groups)
        cv = GroupKFold(n_splits=n_splits)
        cv_scores = cross_val_score(
            model,
            X,
            y,
            cv=cv,
            groups=groups,
            scoring="neg_root_mean_squared_error",
        )
        cv_label = f"GroupKFold({n_splits}) by event, {n_groups} groups"
    else:
        cv_scores = cross_val_score(
            model, X, y, cv=3, scoring="neg_root_mean_squared_error"
        )
        cv_label = "3-fold"

    rmse = float(-cv_scores.mean())
    rmse_std = float((-cv_scores).std())

    model.fit(X, y)
    logger.info(
        "XGBoost model trained — %s CV RMSE: %.4f (±%.4f)",
        cv_label,
        rmse,
        rmse_std,
    )

    from mlflow.models import infer_signature  # type: ignore[import-untyped]

    signature = infer_signature(X, model.predict(X))
    uc_model_name = f"{catalog}.{schema}.{spec.model_name}"
    summary = track_experiment(
        experiment_name=EXPERIMENT_NAME,
        params={str(k): str(v) for k, v in params.items()},
        metrics={"rmse": rmse, "cv_std": rmse_std},
        run_name=f"xgb_pace_{season}_{spec.name}",
        model=model,
        registered_model_name=uc_model_name,
        signature=signature,
    )
    logger.info("MLflow run tracked: %s", summary.get("run_id"))

    # ── Step 3: Promote to @champion only if the candidate improves ────────
    # The alias is per model name, so a lap candidate can never displace the
    # aggregate champion (their targets and RMSE scales are not comparable).
    tolerance = float(os.environ.get("F1_PROMOTION_TOLERANCE", "0.0"))
    incumbent_rmse = get_champion_metric(
        catalog=catalog,
        schema=schema,
        model_name=spec.model_name,
        metric="rmse",
    )
    promote = should_promote(rmse, incumbent_rmse, tolerance=tolerance)
    alias = "champion" if promote else "challenger"
    if incumbent_rmse is None:
        logger.info(
            "No incumbent champion found for '%s' — promoting candidate "
            "(CV RMSE %.4f).",
            spec.model_name,
            rmse,
        )
    elif promote:
        logger.info(
            "Candidate CV RMSE %.4f beats incumbent %.4f — promoting to @champion.",
            rmse,
            incumbent_rmse,
        )
    else:
        logger.info(
            "Candidate CV RMSE %.4f does not beat incumbent %.4f — keeping "
            "@champion, registering candidate as @challenger.",
            rmse,
            incumbent_rmse,
        )
    registered_path = register_champion_model(
        model_name=spec.model_name,
        catalog=catalog,
        schema=schema,
        alias=alias,
    )
    logger.info("Model registered at: %s", registered_path)
    logger.info("=" * 60)
    logger.info("TRAIN COMPLETE — Season %d (schema=%s)", season, spec.name)
    logger.info("=" * 60)


def run_predict(
    season: int,
    catalog: str = CATALOG,
    schema: str = SCHEMA,
    training_schema: str = "aggregate",
) -> None:
    """Score a Gold table with the schema's ``@champion`` model.

    The prediction table is ``<catalog>.<schema>.<source_table>_predictions``.
    It carries the schema's identity keys, the prediction, the model name and a
    UTC scoring timestamp. Scoring a table that was also used for training is
    in-sample; this mode exists to exercise the serving contract, not to claim
    an accuracy number.

    Args:
        season: F1 season year, used only for logging.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        training_schema: ``aggregate`` or ``lap``.
    """
    spec = resolve_training_schema(training_schema)
    logger.info("=" * 60)
    logger.info(
        "DATABRICKS PREDICT MODE — Season %d (%s.%s, schema=%s)",
        season,
        catalog,
        schema,
        spec.name,
    )
    logger.info("=" * 60)

    from pyspark.sql import SparkSession  # type: ignore[import-untyped]

    spark = SparkSession.builder.getOrCreate()
    source_tbl = f"{catalog}.{schema}.{spec.table}"
    if not spark.catalog.tableExists(source_tbl):
        msg = f"Gold table '{source_tbl}' does not exist; run the DLT pipeline first."
        raise RuntimeError(msg)

    rows = spark.table(source_tbl).toPandas()
    if rows.empty:
        msg = f"Gold table '{source_tbl}' returned no rows to score."
        raise RuntimeError(msg)

    X = prepare_feature_frame(rows, spec)  # noqa: N806
    model_uri = f"models:/{catalog}.{schema}.{spec.model_name}@champion"
    logger.info("Loading champion model '%s'…", model_uri)

    import mlflow.pyfunc  # type: ignore[import-untyped]

    mlflow.set_registry_uri("databricks-uc")
    model = mlflow.pyfunc.load_model(model_uri)
    predictions = model.predict(X)

    output = build_prediction_frame(
        rows,
        predictions,
        spec,
        model_name=spec.model_name,
    )
    target_tbl = f"{catalog}.{schema}.{spec.table}_predictions"
    (
        spark.createDataFrame(output)
        .write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target_tbl)
    )
    logger.info("Wrote %d predictions to '%s'.", len(output), target_tbl)
    logger.info("=" * 60)
    logger.info("PREDICT COMPLETE — Season %d (schema=%s)", season, spec.name)
    logger.info("=" * 60)


def run_ingest(
    season: int,
    catalog: str = CATALOG,
    schema: str = SCHEMA,
    round_number: int | None = None,
    all_completed: bool = False,
) -> None:
    """Land real FastF1 race laps into the raw_telemetry Unity Catalog Volume.

    This is the first task of the race-weekend job, and it is what makes the
    DLT Bronze layer real instead of synthetic. Each round is written to its own
    Parquet directory (``season=<year>/round=<NN>/``) so re-runs are idempotent
    and Auto Loader can process rounds incrementally.

    Ingestion is best-effort per round: a FastF1 hiccup (or unavailable lap
    timing) skips that round with a warning rather than failing the whole job,
    mirroring the ``continue-on-error`` philosophy of the local ingestion step.

    Args:
        season: F1 season year.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        round_number: Explicit round to ingest. When None, resolves to every
            completed round (if ``all_completed``) or the most recent race.
        all_completed: When True (and no explicit round), ingest every round
            already raced this season.
    """
    logger.info("=" * 60)
    logger.info("DATABRICKS INGEST MODE — Season %d (%s.%s)", season, catalog, schema)
    logger.info("=" * 60)

    from f1_predictions.databricks.volume_ingest import volume_root

    rounds = _resolve_ingest_rounds(season, round_number, all_completed)
    if not rounds:
        logger.warning("No completed race to ingest for season %d.", season)
        return

    _ensure_volume_dir(volume_root(catalog, schema))

    ingested = 0
    for rnd in rounds:
        if _ingest_round_to_volume(season, rnd, catalog, schema):
            ingested += 1

    logger.info(
        "INGEST COMPLETE — %d/%d round(s) landed in %s",
        ingested,
        len(rounds),
        volume_root(catalog, schema),
    )
    logger.info("=" * 60)


def _resolve_ingest_rounds(
    season: int,
    round_number: int | None,
    all_completed: bool,
) -> list[int]:
    """Resolve which rounds the ingest task should process.

    Args:
        season: F1 season year.
        round_number: Explicit round override, or None to auto-resolve.
        all_completed: Ingest the whole season's completed rounds when no
            explicit round is given.

    Returns:
        Ascending list of round numbers to ingest (possibly empty).
    """
    if round_number is not None:
        return [round_number]

    from f1_predictions.databricks.volume_ingest import completed_round_numbers
    from f1_predictions.utils.race_detector import (
        detect_last_race,
        get_event_schedule,
    )

    if all_completed:
        try:
            return completed_round_numbers(get_event_schedule(season))
        except Exception as exc:
            logger.warning("Could not resolve completed rounds (%s).", exc)
            return []

    last = detect_last_race(season=season, days_back=7)
    return [int(last["round"])] if last is not None else []


def _ensure_volume_dir(path: str) -> None:
    """Best-effort create the Volume directory so Auto Loader has a target.

    Args:
        path: Absolute Volume path to create.
    """
    try:
        from pyspark.dbutils import DBUtils  # type: ignore[import-untyped]
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        DBUtils(spark).fs.mkdirs(path)
        logger.debug("Ensured Volume directory exists: %s", path)
    except Exception as exc:
        logger.debug("Skipping mkdirs for %s (%s).", path, exc)


def _ingest_round_to_volume(
    season: int,
    round_number: int,
    catalog: str,
    schema: str,
) -> bool:
    """Ingest one round's laps from FastF1 into the Volume as Parquet.

    Args:
        season: F1 season year.
        round_number: Round number to ingest.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.

    Returns:
        True if the round was written, False if it was skipped or failed.
    """
    from f1_predictions.databricks.volume_ingest import (
        build_bronze_laps,
        round_volume_path,
    )

    try:
        from f1_predictions.ingestion.fastf1_client import load_session
        from f1_predictions.ingestion.session_loader import load_race

        session, key = load_session(season, round_number, "R")
        race = load_race(session, key)
        bronze_df = build_bronze_laps(
            race.laps,
            season=season,
            round_number=round_number,
            event_name=key.event_name,
        )
    except Exception as exc:
        logger.warning(
            "Could not build Bronze laps for %d R%02d (%s). Skipping round.",
            season,
            round_number,
            exc,
        )
        return False

    try:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        target = round_volume_path(catalog, schema, season, round_number)
        spark.createDataFrame(bronze_df).write.mode("overwrite").parquet(target)
        logger.info(
            "Landed %d laps for %d R%02d -> %s",
            len(bronze_df),
            season,
            round_number,
            target,
        )
    except Exception:
        logger.exception(
            "Failed to write Bronze laps for %d R%02d.", season, round_number
        )
        return False
    return True


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


# S3 configuration values the dashboard publisher needs, resolved from the
# Databricks secret scope when they are not already present in the environment.
_S3_CONFIG_ENV_VARS = (
    "SUPABASE_S3_ENDPOINT_URL",
    "SUPABASE_S3_ACCESS_KEY",
    "SUPABASE_S3_SECRET_KEY",
    "SUPABASE_S3_BUCKET_NAME",
)

# Optional Vercel Deploy Hook, resolved from the same scope when set. Publishing
# new artifacts is not enough on its own: the dashboard pulls reports/ at build
# time and derives its round list from getStaticPaths, so a rebuilt site is what
# actually makes a newly published round reachable.
_DEPLOY_HOOK_ENV_VAR = "F1_VERCEL_DEPLOY_HOOK_URL"


def _load_secrets_from_databricks(env_vars: tuple[str, ...], label: str) -> None:
    """Populate env vars from the ``f1_secrets`` scope when they are unset.

    Values are written straight into the environment and never logged; only a
    count of the values that could not be resolved is emitted, so neither
    credential material nor credential names reach the logs.

    Args:
        env_vars: Environment variable names, also used as the secret keys.
        label: Human-readable group name used in the debug messages.
    """
    try:
        from pyspark.dbutils import DBUtils  # type: ignore[import-untyped]
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        dbutils = DBUtils(spark)
        unresolved = 0
        for env_var in env_vars:
            if os.environ.get(env_var):
                continue
            try:
                os.environ[env_var] = dbutils.secrets.get(
                    scope="f1_secrets", key=env_var
                )
            except Exception:
                unresolved += 1
        if unresolved:
            logger.debug(
                "%d/%d %s values were not present in the 'f1_secrets' scope; "
                "falling back to environment variables.",
                unresolved,
                len(env_vars),
                label,
            )
    except Exception:
        logger.debug(
            "Databricks secrets lookup skipped; using env var %s config.", label
        )


def _load_s3_secrets_from_databricks() -> None:
    """Populate the S3 configuration env vars from ``f1_secrets`` when unset."""
    _load_secrets_from_databricks(_S3_CONFIG_ENV_VARS, "S3 configuration")


def _trigger_dashboard_rebuild() -> None:
    """Ask Vercel to rebuild so newly published rounds become reachable.

    Best-effort by design: an unset hook, a missing ``requests``, or a failed
    request is logged and swallowed. The export task must never fail because the
    site could not be poked — the next deploy still picks the bundle up.
    """
    _load_secrets_from_databricks((_DEPLOY_HOOK_ENV_VAR,), "deploy hook")
    hook_url = os.environ.get(_DEPLOY_HOOK_ENV_VAR)
    if not hook_url:
        logger.info(
            "%s is not set — skipping the dashboard rebuild; the next deploy will "
            "pick up the published bundle.",
            _DEPLOY_HOOK_ENV_VAR,
        )
        return

    try:
        import requests
    except ImportError:
        logger.warning("requests is unavailable; cannot trigger a dashboard rebuild.")
        return

    try:
        response = requests.post(hook_url, timeout=30)
    except Exception as exc:
        logger.warning("Dashboard rebuild trigger failed (%s); redeploy manually.", exc)
        return

    if response.ok:
        logger.info("Dashboard rebuild triggered (HTTP %d).", response.status_code)
    else:
        logger.warning(
            "Dashboard rebuild trigger returned HTTP %d; redeploy manually.",
            response.status_code,
        )


def run_export(season: int, catalog: str = CATALOG, schema: str = SCHEMA) -> None:
    """Publish the season's dashboard artifacts to S3-compatible storage.

    This is the "serving" half of the Databricks → dashboard channel: the
    season's report bundle under ``reports/<season>`` is uploaded to object
    storage, and the dashboard's prebuild step
    (``dashboard/scripts/fetch-dashboard-data.mjs``) pulls it back down.

    Publishing is best-effort and non-fatal: a missing bucket, missing
    credentials, or an empty season logs a warning and returns rather than
    failing the job (the notification task has already done its work).

    Args:
        season: F1 season year to publish.
        catalog: Unity Catalog catalog name (context only).
        schema: Unity Catalog schema name (context only).
    """
    logger.info("=" * 60)
    logger.info("DATABRICKS EXPORT MODE — Season %d (%s.%s)", season, catalog, schema)
    logger.info("=" * 60)

    from f1_predictions.utils.dashboard_publish import publish_dashboard_data

    _load_s3_secrets_from_databricks()

    try:
        summary = publish_dashboard_data(PROJECT_ROOT / "reports", season)
    except Exception as exc:
        logger.warning(
            "Dashboard publish skipped for season %d (%s). "
            "Set SUPABASE_S3_* / f1_secrets to enable cloud serving.",
            season,
            exc,
        )
        return

    logger.info("Dashboard publish summary: %s", summary)
    _trigger_dashboard_rebuild()
    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE — Season %d", season)
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
            "Databricks Lakeflow Job entry point for the F1 2026 Predictions "
            "Pipeline. Dispatches to ingest, train, predict, notify or export "
            "mode based on --run-mode."
        ),
    )
    parser.add_argument(
        "--run-mode",
        required=True,
        choices=["ingest", "train", "predict", "notify", "export"],
        help="Execution mode: 'ingest' lands FastF1 laps in the raw_telemetry "
        "Volume; 'train' trains XGBoost and promotes @champion on improvement; "
        "'predict' scores a Gold table with the schema's @champion; 'notify' "
        "dispatches the race verdict to Gmail and Discord; 'export' publishes "
        "the dashboard bundle to object storage.",
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
        "--training-schema",
        choices=TRAINING_SCHEMA_CHOICES,
        default="aggregate",
        help="Feature contract to use for train/predict: 'aggregate' is the "
        "historical per-driver fastest-lap table; 'lap' is the shared per-lap "
        "LapTime_s table (Task 21.3).",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        help="F1 round number override for ingest and notifications.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass race weekend gate and force execution.",
    )
    parser.add_argument(
        "--all-completed",
        action="store_true",
        help="For --run-mode ingest: ingest every completed round this season.",
    )

    args = parser.parse_args()
    logger.info(
        "Databricks entrypoint: mode=%s, season=%d, catalog=%s, schema=%s, "
        "training_schema=%s, force=%s",
        args.run_mode,
        args.season,
        args.catalog,
        args.schema,
        args.training_schema,
        args.force,
    )

    if not args.force and not is_race_window_active(args.season):
        logger.info(
            "Non-race day detected (season %d). Skipping execution.",
            args.season,
        )
        return

    if args.run_mode == "ingest":
        run_ingest(
            season=args.season,
            catalog=args.catalog,
            schema=args.schema,
            round_number=args.round,
            all_completed=args.all_completed,
        )
    elif args.run_mode == "train":
        run_train(
            season=args.season,
            catalog=args.catalog,
            schema=args.schema,
            training_schema=args.training_schema,
        )
    elif args.run_mode == "predict":
        run_predict(
            season=args.season,
            catalog=args.catalog,
            schema=args.schema,
            training_schema=args.training_schema,
        )
    elif args.run_mode == "notify":
        run_notify(
            season=args.season,
            catalog=args.catalog,
            schema=args.schema,
            round_number=args.round,
        )
    elif args.run_mode == "export":
        run_export(season=args.season, catalog=args.catalog, schema=args.schema)


if __name__ == "__main__":
    main()
