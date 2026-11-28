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


def _resolve_round(
    season: int,
    round_number: int | None,
    phase: str = "post-race",
) -> int | None:
    """Resolve the round to report: explicit override, upcoming, or last completed."""
    if round_number is not None:
        return int(round_number)

    if phase == "pre-race":
        from f1_predictions.utils.race_detector import detect_upcoming_race

        upcoming = detect_upcoming_race(season=season, days_ahead=4)
        if upcoming is None:
            return None
        return int(upcoming["round"])

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


def stage_season_bundle(
    season: int,
    catalog: str,
    schema: str,
    project_root: Path,
) -> tuple[Path, Path]:
    """Seed a writable staging copy of the season bundle.

    Shared by the report and simulation run-modes: both need the accumulated
    season tree (previous rounds, ``calendar.json``, summaries) plus a scratch
    directory the pipeline can write to before the Volume is replaced.

    Args:
        season: F1 season year.
        catalog: Unity Catalog catalog that holds the bundle Volume.
        schema: Unity Catalog schema that holds the bundle Volume.
        project_root: Bundle workspace root, used as the last-resort seed.

    Returns:
        ``(bundle_root, season_dir)``: the Volume root and the staging copy of
        the season tree.
    """
    bundle = volume_bundle_root(catalog, schema)
    staging = _staging_root()
    reports_dir = staging / "reports"
    season_dir = _seed_reports(season, bundle, project_root, reports_dir)
    return bundle, season_dir


def publish_season_bundle(bundle: Path, season_dir: Path) -> int:
    """Replace the Volume's season tree with a staged one.

    Args:
        bundle: Bundle Volume root.
        season_dir: Staged ``.../reports/<season>`` directory.

    Returns:
        Number of files copied to the Volume.
    """
    bundle.mkdir(parents=True, exist_ok=True)
    destination = bundle / season_dir.name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(season_dir, destination)
    return sum(1 for path in destination.rglob("*") if path.is_file())


def generate_report_bundle(
    season: int,
    catalog: str,
    schema: str,
    project_root: Path,
    round_number: int | None = None,
    force: bool = False,
    preserve_narratives: bool = False,
    phase: str = "post-race",
) -> dict[str, Any]:
    """Generate a round's report (pre-race or post-race) and sync to the Volume.

    Args:
        season: F1 season year.
        catalog: Unity Catalog catalog that holds the bundle Volume.
        schema: Unity Catalog schema that holds the bundle Volume.
        project_root: Bundle workspace root, used to import ``scripts`` and to
            seed the first run from the committed reports.
        round_number: Explicit round override; when None the upcoming race
            (``phase="pre-race"``) or last completed race (``phase="post-race"``)
            is used.
        force: Rebuild even when the bundle already contains the round's
            marker artifact.
        preserve_narratives: Keep the existing ``report_round_N.md`` and
            ``predicted_report_round_N.md`` files. Used when only the derived
            charts need refreshing after a prediction regeneration, so a run
            without a Gemini key does not replace good copy with fallback text.
        phase: ``"post-race"`` (default) or ``"pre-race"``. Controls round
            auto-detection and which completion marker artifact is verified.

    Returns:
        Summary with ``generated``, ``season``, ``round``, ``files`` and
        ``bundle`` keys.

    Raises:
        RuntimeError: When the pipeline finishes without writing the expected
            marker artifact, so a broken run fails the task instead of
            publishing an incomplete bundle.
    """
    target_round = _resolve_round(season, round_number, phase=phase)
    if target_round is None:
        logger.info(
            "No %s race found for season %d; nothing to report.", phase, season
        )
        return {"generated": False, "season": season, "round": None}

    # Point FastF1 at instance-local scratch before the pipeline reads settings.
    # A multi-round rebuild loads many sessions in one task, so the cache matters.
    _configure_fastf1_cache()

    bundle, season_dir = stage_season_bundle(
        season, catalog, schema, project_root
    )
    reports_dir = season_dir.parent

    marker_name = (
        f"predicted_lap_positions_round_{target_round}.json"
        if phase == "pre-race"
        else f"actual_results_round_{target_round}.json"
    )
    marker_path = season_dir / "summaries" / marker_name
    if marker_path.exists() and not force:
        logger.info(
            "Round %d already has %s artifacts in the bundle (%s); skipping. "
            "Use force=True to rebuild.",
            target_round,
            phase,
            marker_path,
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

    preserved_narratives: dict[Path, str] = {}
    if preserve_narratives:
        for path in season_dir.rglob(f"*report_round_{target_round}.md"):
            preserved_narratives[path] = path.read_text(encoding="utf-8")
        logger.info(
            "Preserving %d narrative file(s) for round %d",
            len(preserved_narratives),
            target_round,
        )

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

    for path, text in preserved_narratives.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    if not marker_path.exists():
        msg = (
            f"Report generation finished without {marker_path}. "
            "The bundle was not published."
        )
        raise RuntimeError(msg)

    files = publish_season_bundle(bundle, season_dir)
    destination = bundle / str(season)
    logger.info(
        "Report bundle (%s) for %d R%02d synced to %s (%d files)",
        phase,
        season,
        target_round,
        destination,
        files,
    )
    return {
        "generated": True,
        "season": season,
        "round": target_round,
        "phase": phase,
        "files": files,
        "bundle": str(destination),
    }
