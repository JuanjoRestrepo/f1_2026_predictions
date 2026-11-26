"""Run the repository's data and simulation pipeline inside Databricks.

The local pipeline reads and writes ``data/{raw,processed,outputs}`` on disk.
Those directories do not exist in a Databricks workspace, which is why the
race simulation used to run only on a developer machine. The pipeline's roots
are already settings-driven (``F1_DATA_*_DIR``), so a cloud run is the same
code with different roots: nothing in the feature engineering is reimplemented.

Layout on the Volume mirrors the repository::

    /Volumes/<catalog>/<schema>/f1_data/
        raw/laps/season=<year>/round=<NN>/race_laps.parquet
        processed/laps/season=<year>/round=<NN>/race_laps.parquet
        processed/weather/season=<year>/round=<NN>/race_weather.parquet
        outputs/laps/season=<year>/round=<NN>/race_laps.parquet

``backfill_seasons`` builds that tree from FastF1. ``simulate_round`` reads it
and writes the round's ``predictions.csv`` into the ``dashboard_bundle``
Volume, which the existing export task then publishes.

Why a full backfill is required: ``scripts/simulate_race.py`` trains its
stacking and quantile models on every season before the target one (2022
through ``year - 1``). A cloud simulation with only the 2026 rounds in the
Volume has no training window, so the historical seasons must be present.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Name of the managed Volume that holds the pipeline's data tree.
DATA_VOLUME_NAME = "f1_data"

#: Seasons the simulator trains on. Keep in sync with
#: ``scripts/simulate_race.py`` (``train_years = range(2022, year)``).
TRAINING_SEASONS: tuple[int, ...] = (2022, 2023, 2024, 2025)


def volume_data_root(catalog: str, schema: str) -> Path:
    """Return the root of the pipeline data tree on the Unity Catalog Volume.

    Args:
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.

    Returns:
        Absolute Volume path, e.g. ``/Volumes/main/f1_2026_prod/f1_data``.
    """
    return Path(f"/Volumes/{catalog}/{schema}/{DATA_VOLUME_NAME}")


def configure_data_paths(
    catalog: str,
    schema: str,
    reports_dir: Path | None = None,
) -> Path:
    """Point the pipeline settings at the Volume instead of ``./data``.

    ``get_settings`` is ``lru_cache``-decorated, so the cache is cleared after
    the environment is updated. Every pipeline entry point resolves its roots
    inside the function, which makes the clear sufficient.

    Args:
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        reports_dir: Optional override for ``F1_REPORTS_DIR`` (the staged
            report tree). Left untouched when ``None``.

    Returns:
        The Volume data root that was configured.
    """
    root = volume_data_root(catalog, schema)
    roots = {
        "F1_DATA_RAW_DIR": root / "raw",
        "F1_DATA_PROCESSED_DIR": root / "processed",
        "F1_DATA_OUTPUTS_DIR": root / "outputs",
    }
    if reports_dir is not None:
        roots["F1_REPORTS_DIR"] = Path(reports_dir)

    for key, value in roots.items():
        os.environ[key] = str(value)

    from f1_predictions.databricks.report_bundle import _configure_fastf1_cache
    from f1_predictions.utils.config import get_settings

    # The cache must be set before the settings singleton is rebuilt, otherwise
    # it defaults to a workspace path that is too small for a season backfill.
    _configure_fastf1_cache()
    get_settings.cache_clear()
    logger.info("Pipeline data roots now resolve inside %s", root)
    return root


def completed_rounds(season: int) -> list[int]:
    """Return the rounds of ``season`` whose race day is already over.

    Args:
        season: F1 season year.

    Returns:
        Ascending round numbers, empty when the calendar cannot be read.
    """
    from f1_predictions.databricks.volume_ingest import completed_round_numbers
    from f1_predictions.utils.race_detector import get_event_schedule

    try:
        return completed_round_numbers(get_event_schedule(season))
    except Exception as exc:
        logger.warning("Could not resolve completed rounds for %d (%s).", season, exc)
        return []


def event_name_for_round(season: int, round_number: int) -> str:
    """Resolve a round's official event name from the FastF1 schedule.

    Args:
        season: F1 season year.
        round_number: Round number within the season.

    Returns:
        The schedule's ``EventName`` for that round.

    Raises:
        ValueError: When the schedule has no matching round.
    """
    from f1_predictions.utils.race_detector import get_event_schedule

    schedule = get_event_schedule(season)
    rounds = schedule[schedule["RoundNumber"].astype(int) == int(round_number)]
    if rounds.empty:
        msg = f"No event found for season {season} round {round_number}."
        raise ValueError(msg)
    return str(rounds.iloc[0]["EventName"])


def _ensure_project_on_path(project_root: Path) -> None:
    """Make ``scripts`` importable from the bundle workspace root."""
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _gold_laps_path(root: Path, season: int, round_number: int) -> Path:
    """Return the Gold laps path for a round inside the data Volume."""
    return (
        root
        / "outputs"
        / "laps"
        / f"season={season}"
        / f"round={round_number:02d}"
        / "race_laps.parquet"
    )


def backfill_seasons(
    seasons: list[int],
    catalog: str,
    schema: str,
    project_root: Path,
    round_number: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build the pipeline's raw/processed/Gold tree on the Volume from FastF1.

    Existing Gold Parquets are skipped before the session is downloaded, so a
    re-run only fetches the rounds that are still missing. ``overwrite=True``
    re-downloads and recomputes every requested round.

    Args:
        seasons: Season years to backfill, in processing order.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        project_root: Bundle workspace root (holds ``scripts/``).
        round_number: Restrict the backfill to this round in every season.
        overwrite: Recompute rounds whose Gold Parquet already exists.

    Returns:
        ``{"root": ..., "seasons": {season: {"ingested": [...], "skipped": [...]}}}``.
    """
    root = configure_data_paths(catalog, schema)
    _ensure_project_on_path(project_root)

    from scripts.ingest_season import ingest_round

    summary: dict[str, Any] = {"root": str(root), "seasons": {}}
    for season in seasons:
        rounds = (
            [int(round_number)]
            if round_number is not None
            else completed_rounds(season)
        )
        ingested: list[int] = []
        skipped: list[int] = []

        for rnd in rounds:
            if not overwrite and _gold_laps_path(root, season, rnd).exists():
                logger.info(
                    "Skipping %d R%02d: Gold already exists in the Volume.",
                    season,
                    rnd,
                )
                skipped.append(rnd)
                continue
            try:
                ok = ingest_round(season, rnd, overwrite=overwrite)
            except Exception:
                logger.exception("Backfill failed for %d R%02d.", season, rnd)
                ok = False
            if ok:
                ingested.append(rnd)
            else:
                logger.warning("Backfill produced no Gold for %d R%02d.", season, rnd)

        summary["seasons"][str(season)] = {
            "ingested": ingested,
            "skipped": skipped,
        }
        logger.info(
            "Backfill %d complete: %d ingested, %d already present.",
            season,
            len(ingested),
            len(skipped),
        )

    return summary


def simulate_round(
    season: int,
    round_number: int,
    catalog: str,
    schema: str,
    project_root: Path,
    event_name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run ``scripts/simulate_race.py`` against the Volume data tree.

    The report bundle is staged first so the entry-list filter can read the
    round's official classification (``actual_results_round_N.json``) when the
    race has already been run, and the previous round's classification otherwise.
    The regenerated ``predictions.csv`` is then copied back to the bundle
    Volume, ready for the report and export tasks.

    Args:
        season: F1 season year.
        round_number: Round to simulate.
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        project_root: Bundle workspace root (holds ``scripts/``).
        event_name: Event name override; resolved from the schedule when None.
        force: Rebuild even when the round's predictions already exist.

    Returns:
        Summary with ``generated``, ``season``, ``round``, ``event``,
        ``predictions`` and ``bundle`` keys.

    Raises:
        RuntimeError: When the simulation finishes without writing
            ``predictions.csv``, so a broken run never publishes stale data.
    """
    from f1_predictions.databricks.report_bundle import (
        publish_season_bundle,
        stage_season_bundle,
    )
    from f1_predictions.utils.event_slug import event_slug

    target_event = event_name or event_name_for_round(season, round_number)
    bundle, season_dir = stage_season_bundle(season, catalog, schema, project_root)
    predictions = season_dir / event_slug(target_event) / "results" / "predictions.csv"

    if predictions.exists() and not force:
        logger.info(
            "Predictions for %d R%02d already exist (%s); skipping. "
            "Use force=True to rebuild.",
            season,
            round_number,
            predictions,
        )
        return {
            "generated": False,
            "season": season,
            "round": round_number,
            "event": target_event,
            "predictions": str(predictions),
            "reason": "already-present",
        }

    configure_data_paths(catalog, schema, reports_dir=season_dir.parent)
    _ensure_project_on_path(project_root)

    from scripts.simulate_race import run_race_simulation

    run_race_simulation(
        year=season,
        round_number=round_number,
        event_name=target_event,
    )

    if not predictions.exists():
        msg = f"Simulation finished without {predictions}. The bundle was not updated."
        raise RuntimeError(msg)

    files = publish_season_bundle(bundle, season_dir)
    logger.info(
        "Simulation for %d R%02d synced to %s (%d files)",
        season,
        round_number,
        bundle / str(season),
        files,
    )
    return {
        "generated": True,
        "season": season,
        "round": round_number,
        "event": target_event,
        "predictions": str(predictions),
        "files": files,
        "bundle": str(bundle / str(season)),
    }
