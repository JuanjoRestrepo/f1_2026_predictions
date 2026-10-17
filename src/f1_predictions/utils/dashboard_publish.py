"""Publish dashboard data artifacts to S3-compatible object storage.

The Next.js dashboard reads its race intelligence from ``reports/<season>/``
(see ``dashboard/src/utils/fileReader.ts``). That data has historically been
committed to git; with orchestration moved to Databricks, the cloud job becomes
the producer. This module packages a season's report artifacts and uploads them
to object storage, and the dashboard's prebuild step pulls them back down.

Layout written to the bucket::

    <prefix>/<season>/manifest.json     # written LAST — the completeness signal
    <prefix>/<season>/<relative path>   # mirrors reports/<season>/ exactly

The manifest is written after all artifacts so a consumer never sees a partial
bundle: if ``manifest.json`` is present, the whole season has landed.
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from f1_predictions.utils.cloud_cache import get_s3_client

logger = logging.getLogger(__name__)


class DashboardS3Client(Protocol):
    """Structural type for the S3 client the dashboard publisher needs.

    Declaring only the single method this module calls keeps it decoupled from
    botocore and trivially testable with an in-memory fake.
    """

    def put_object(self, **kwargs: object) -> object:
        """Upload one object (Bucket/Key/Body/ContentType as kwargs)."""
        raise NotImplementedError


# Object-key prefix (folder) inside the bucket that holds the dashboard bundle.
DASHBOARD_OBJECT_PREFIX = "dashboard"

# Name of the completeness-signal manifest.
MANIFEST_FILENAME = "manifest.json"

# Only these artifact types are published — the exact set the dashboard's
# fileReader consumes. An allowlist keeps unrelated/large build artifacts out.
ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {".json", ".csv", ".md", ".png", ".svg", ".html", ".txt"}
)

# OS/editor cruft that must never be published.
_EXCLUDED_NAMES: frozenset[str] = frozenset({".DS_Store", "Thumbs.db"})

# Matches the ``round_<N>`` convention used across dashboard artifact filenames.
_ROUND_PATTERN = re.compile(r"round_(\d+)")

_CONTENT_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".html": "text/html",
    ".txt": "text/plain",
}


def season_directory(reports_dir: Path, season: int) -> Path:
    """Return the ``reports/<season>`` directory for a season.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.

    Returns:
        Path to the season's report directory.
    """
    return reports_dir / str(season)


def _is_publishable(path: Path) -> bool:
    """Return True if a file is a dashboard artifact worth publishing."""
    if path.name in _EXCLUDED_NAMES or path.name.startswith("."):
        return False
    return path.suffix.lower() in ALLOWED_SUFFIXES


def collect_dashboard_files(reports_dir: Path, season: int) -> list[Path]:
    """Collect every publishable dashboard artifact for a season.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.

    Returns:
        Sorted list of absolute artifact paths (empty if the season is absent).
    """
    season_dir = season_directory(reports_dir, season)
    if not season_dir.is_dir():
        return []
    return sorted(
        path
        for path in season_dir.rglob("*")
        if path.is_file() and _is_publishable(path)
    )


def discover_rounds(files: Iterable[Path]) -> list[int]:
    """Infer the rounds present from artifact filenames.

    Args:
        files: Artifact paths (any directory).

    Returns:
        Ascending, de-duplicated list of round numbers found in file names.
    """
    rounds: set[int] = set()
    for path in files:
        rounds.update(int(m.group(1)) for m in _ROUND_PATTERN.finditer(path.name))
    return sorted(rounds)


def build_dashboard_manifest(
    reports_dir: Path,
    season: int,
    files: list[Path] | None = None,
    directory_rounds: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Build the JSON manifest that describes a published season bundle.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.
        files: Pre-collected artifact paths. Recollected when omitted.
        directory_rounds: On-disk race directory to round-number map, read from
            the calendar. Supplying it lets a round that only has a
            ``results/predictions.csv`` (a pre-race prediction, no ``round_N``
            anywhere in the file names) still appear in ``rounds`` — the same
            rule the dashboard applies when deciding a round is available.

    Returns:
        Manifest payload with season, timestamp, object prefix, rounds and the
        list of artifact paths relative to ``reports/<season>``.
    """
    season_dir = season_directory(reports_dir, season)
    resolved = (
        files if files is not None else collect_dashboard_files(reports_dir, season)
    )
    relative = [path.relative_to(season_dir).as_posix() for path in resolved]

    rounds = set(discover_rounds(resolved))
    for path in resolved:
        if path.name != "predictions.csv" or path.parent.name != "results":
            continue
        inferred = (directory_rounds or {}).get(path.parent.parent.name)
        if inferred is not None:
            rounds.add(inferred)

    return {
        "season": season,
        "generated_at": datetime.now(UTC).isoformat(),
        "object_prefix": f"{DASHBOARD_OBJECT_PREFIX}/{season}",
        "rounds": sorted(rounds),
        "file_count": len(relative),
        "files": relative,
    }


def _directory_round_map(reports_dir: Path, season: int) -> dict[str, int]:
    """Map race directories on disk to round numbers using the calendar.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.

    Returns:
        Directory name to round number, empty when the calendar is unavailable.
    """
    # Imported lazily: calendar_coverage imports season_directory from this
    # module, so a module-level import here would be circular.
    from f1_predictions.utils.calendar_coverage import load_calendar

    return {race.directory: race.round for race in load_calendar(reports_dir, season)}


def _content_type(relative_path: str) -> str:
    """Map a relative artifact path to an HTTP content type."""
    suffix = posixpath.splitext(relative_path)[1].lower()
    return _CONTENT_TYPES.get(suffix, "application/octet-stream")


def publish_dashboard_data(
    reports_dir: Path,
    season: int,
    *,
    bucket_name: str | None = None,
    prefix: str = DASHBOARD_OBJECT_PREFIX,
    client: DashboardS3Client | None = None,
) -> dict[str, Any]:
    """Upload a season's dashboard artifacts (and a manifest) to object storage.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.
        bucket_name: Bucket to publish into. Falls back to the
            ``SUPABASE_S3_BUCKET_NAME`` environment variable.
        prefix: Object-key prefix for the bundle (default ``dashboard``).
        client: Pre-built S3 client (injected in tests). Built lazily otherwise.

    Returns:
        Summary dict with ``published`` count, ``season``, ``manifest_key`` and
        the published file list. ``published`` is 0 when there is nothing to do.

    Raises:
        ValueError: If no bucket can be resolved and there is data to publish.
    """
    season_dir = season_directory(reports_dir, season)
    files = collect_dashboard_files(reports_dir, season)
    if not files:
        logger.warning(
            "No dashboard artifacts under %s; nothing published.", season_dir
        )
        return {"published": 0, "season": season, "files": []}

    resolved_bucket = bucket_name or os.environ.get("SUPABASE_S3_BUCKET_NAME")
    if not resolved_bucket:
        msg = "bucket_name must be provided or SUPABASE_S3_BUCKET_NAME must be set."
        raise ValueError(msg)

    s3 = client if client is not None else get_s3_client()

    published = 0
    for path in files:
        relative = path.relative_to(season_dir).as_posix()
        key = posixpath.join(prefix, str(season), relative)
        s3.put_object(
            Bucket=resolved_bucket,
            Key=key,
            Body=path.read_bytes(),
            ContentType=_content_type(relative),
        )
        published += 1

    # Manifest last: its presence signals that the bundle is complete.
    manifest = build_dashboard_manifest(
        reports_dir,
        season,
        files,
        directory_rounds=_directory_round_map(reports_dir, season),
    )
    manifest_key = posixpath.join(prefix, str(season), MANIFEST_FILENAME)
    s3.put_object(
        Bucket=resolved_bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "Published %d dashboard artifact(s) + manifest for season %d → s3://%s/%s",
        published,
        season,
        resolved_bucket,
        posixpath.dirname(manifest_key),
    )
    return {
        "published": published,
        "season": season,
        "manifest_key": manifest_key,
        "files": manifest["files"],
    }
