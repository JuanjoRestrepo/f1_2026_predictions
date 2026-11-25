"""Build the race-weekend report bundle inside Databricks.

Before this module the scheduled job only *published* the ``reports/`` tree that
happened to be committed at deploy time (``docs/PLAN_CLOUD_NATIVE_SERVING.md``
§"Current state"). A new round therefore never reached the site unless someone
generated the artifacts on a developer machine and committed them.

This module closes that gap for the post-race artifacts:

1. Seed a staging ``reports/`` tree from the release bundle Volume (or the
   repo on first run) so accumulated predictions and ``calendar.json`` survive.
2. Run ``scripts/master_pipeline.py`` for the completed round, which loads the
   authoritative FastF1 session and writes the actual classification, lap
   positions, tyre intelligence and narrative.
3. Copy the season's bundle to a Unity Catalog Volume.

``run_export`` then publishes that Volume instead of the repository tree.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Name of the managed Volume that holds the release bundle.
BUNDLE_VOLUME_NAME = "dashboard_bundle"


def volume_bundle_root(catalog: str, schema: str) -> Path:
    """Return the root of the release bundle on the Unity Catalog Volume."""
    return Path(f"/Volumes/{catalog}/{schema}/{BUNDLE_VOLUME_NAME}")


def _staging_root() -> Path:
    """Pick a writable scratch directory for the report build.

    ``/local_disk0`` is the instance-local scratch volume Databricks reserves
    for serverless drivers. ``tempfile`` is the fallback when it is absent
    (local test runs).
    """
    local_disk = Path("/local_disk0/f1_report")
    try:
        local_disk.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path(tempfile.mkdtemp(prefix="f1_report_"))
    return local_disk


def _configure_fastf1_cache() -> None:
    """Point FastF1 at ephemeral local disk before the pipeline reads settings.

    The workspace root is not a good cache location: it is small, and on
    serverless the driver may be replaced between tasks.
    """
    if os.environ.get("F1_FASTF1_CACHE_DIR"):
        return
    cache = Path("/local_disk0/f1_fastf1_cache")
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        cache = Path(tempfile.mkdtemp(prefix="f1_fastf1_cache_"))
    os.environ["F1_FASTF1_CACHE_DIR"] = str(cache)


def _resolve_round(season: int, round_number: int | None) -> int | None:
    """Resolve the round to report on: explicit override or last completed."""
    if round_number is not None:
        return int(round_number)

    from f1_predictions.utils.race_detector import detect_last_race

    last = detect_last_race(season=season, days_back=7)
    if last is None:
        return None
    return int(last["round"])


def _seed_reports(
    season: int,
    bundle: Path,
    project_root: Path,
    reports_dir: Path,
) -> Path:
    """Populate the staging directory with the current season bundle.

    Order of preference, most authoritative first:

    1. The bundle Volume — a previous cloud build, already complete.
    2. The published object-storage bundle — the artifacts the site is serving
       right now. Seeding from it means a rebuild adds the new round instead of
       replacing the season with the (partially gitignored) repository tree.
    3. The repository ``reports/`` tree — first run in a fresh workspace.

    A seed failure is logged, not raised: the pipeline can still generate the
    round, it just starts from a thinner base.
    """
    target = reports_dir / str(season)
    if target.exists():
        shutil.rmtree(target)

    volume_season = bundle / str(season)
    if volume_season.exists():
        shutil.copytree(volume_season, target)
        logger.info("Seeded report bundle for %d from Volume %s", season, volume_season)
        return target

    try:
        from f1_predictions.utils.dashboard_publish import download_dashboard_bundle

        summary = download_dashboard_bundle(reports_dir, season)
        if summary["downloaded"] > 0:
            logger.info(
                "Seeded report bundle for %d from %s", season, summary["source"]
            )
            return target
    except Exception as exc:
        logger.warning("Could not seed from object storage: %s", exc)

    repo_season = project_root / "reports" / str(season)
    if repo_season.exists():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(repo_season, target)
        logger.info(
            "Seeded report bundle for %d from repository %s", season, repo_season
        )
    else:
        target.mkdir(parents=True)
        logger.warning(
            "No seed bundle at %s, object storage, or %s; starting from an "
            "empty season tree.",
            volume_season,
            repo_season,
        )
    return target


def generate_report_bundle(
    season: int,
    catalog: str,
    schema: str,
    project_root: Path,
    round_number: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate the completed round's report and sync it to the bundle Volume.

    Args:
        season: F1 season year.
        catalog: Unity Catalog catalog that holds the bundle Volume.
        schema: Unity Catalog schema that holds the bundle Volume.
        project_root: Bundle workspace root, used to import ``scripts`` and to
            seed the first run from the committed reports.
        round_number: Explicit round override; when None the last completed race
            is used.
        force: Rebuild even when the bundle already contains the round's actual
            results.

    Returns:
        Summary with ``generated``, ``season``, ``round``, ``files`` and
        ``bundle`` keys.

    Raises:
        RuntimeError: When the pipeline finishes without writing the actual
            results, so a broken run fails the task instead of publishing an
            incomplete bundle.
    """
    target_round = _resolve_round(season, round_number)
    if target_round is None:
        logger.info("No completed race found for season %d; nothing to report.", season)
        return {"generated": False, "season": season, "round": None}

    bundle = volume_bundle_root(catalog, schema)
    staging = _staging_root()
    reports_dir = staging / "reports"
    season_dir = _seed_reports(season, bundle, project_root, reports_dir)

    actual_results = (
        season_dir / "summaries" / f"actual_results_round_{target_round}.json"
    )
    if actual_results.exists() and not force:
        logger.info(
            "Round %d already has actual results in the bundle (%s); skipping. "
            "Use force=True to rebuild.",
            target_round,
            actual_results,
        )
        return {
            "generated": False,
            "season": season,
            "round": target_round,
            "files": 0,
            "bundle": str(bundle),
            "reason": "already-present",
        }

    os.environ["F1_REPORTS_DIR"] = str(reports_dir)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from scripts import master_pipeline

    # ``REPORTS_BASE`` is read at import time, so point it at staging explicitly
    # even when the module was imported before the environment variable was set.
    master_pipeline.REPORTS_BASE = reports_dir

    argv = [
        "master_pipeline.py",
        "--year",
        str(season),
        "--round",
        str(target_round),
        "--auto",
    ]
    previous_argv = sys.argv
    sys.argv = argv
    try:
        master_pipeline.main()
    finally:
        sys.argv = previous_argv

    if not actual_results.exists():
        msg = (
            f"Report generation finished without {actual_results}. "
            "The bundle was not published."
        )
        raise RuntimeError(msg)

    bundle.mkdir(parents=True, exist_ok=True)
    destination = bundle / str(season)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(season_dir, destination)

    files = sum(1 for path in destination.rglob("*") if path.is_file())
    logger.info(
        "Report bundle for %d R%02d synced to %s (%d files)",
        season,
        target_round,
        destination,
        files,
    )
    return {
        "generated": True,
        "season": season,
        "round": target_round,
        "files": files,
        "bundle": str(destination),
    }
