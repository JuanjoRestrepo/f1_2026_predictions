"""Backfill traffic exposure labels into existing Gold-layer lap files.

The Gold feature pipeline now computes traffic exposure labels
(``traffic_ahead_s``, ``traffic_nearest_s``, ``in_clean_air``) for every session
it builds, which covers every round ingested from now on. Rounds ingested
before that step existed carry no labels, and since the model trains on
whatever the Gold files contain, the historical rounds need a one-off backfill.

Why not simply re-run the feature pipeline for every round: the current
pipeline code also emits fifteen columns that the ingested Gold files do not
carry (``Track_Evolution_Factor``, the EWMA form features, the circuit config
block, and others). A full rebuild would therefore change the model's feature
set far beyond the labels this script adds, and would make the effect of the
labels impossible to attribute. Rebuilding the Gold layer is a separate,
deliberate decision; this script changes exactly three columns.

Usage::

    uv run python scripts/backfill_traffic_exposure.py            # dry run
    uv run python scripts/backfill_traffic_exposure.py --apply

Idempotency: files that already carry the labels are skipped unless
``--force`` is passed, and re-running the label computation on unchanged laps
reproduces identical values.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from f1_predictions.features.traffic_exposure import (
    TRAFFIC_COLUMNS,
    add_traffic_exposure,
)
from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.ingestion.parquet_writer import DataType, write_parquet
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)

_PATH_PATTERN = re.compile(r"season=(\d{4})/round=(\d{2})/race_laps\.parquet$")


def _parse_key(path: Path) -> SessionKey | None:
    """Recover the SessionKey from a Gold-lap partition path."""
    match = _PATH_PATTERN.search(path.as_posix())
    if match is None:
        return None
    frame = pd.read_parquet(path, columns=["EventName"])
    event = str(frame["EventName"].iloc[0]) if len(frame) else "Unknown"
    return SessionKey(
        year=int(match.group(1)),
        round_number=int(match.group(2)),
        identifier="R",
        event_name=event,
    )


def _verify(labelled: pd.DataFrame, original: pd.DataFrame) -> None:
    """Assert the backfill added columns and changed nothing else.

    Raises:
        ValueError: If a row was lost, a row was added, a pre-existing column
            was altered, or a label column is missing.
    """
    if len(labelled) != len(original):
        msg = f"Row count changed: {len(original)} -> {len(labelled)}"
        raise ValueError(msg)

    added = [c for c in labelled.columns if c not in original.columns]
    lost = [c for c in original.columns if c not in labelled.columns]
    if lost:
        msg = f"Preexisting columns lost: {lost}"
        raise ValueError(msg)
    for column in TRAFFIC_COLUMNS:
        if column not in added:
            msg = f"Expected label column '{column}' was not added (added={added})"
            raise ValueError(msg)

    for column in original.columns:
        before = original[column]
        after = labelled[column]
        if pd.api.types.is_numeric_dtype(before) and not pd.api.types.is_bool_dtype(
            before
        ):
            same = np.allclose(
                before.to_numpy(dtype=float),
                pd.to_numeric(after, errors="coerce").to_numpy(dtype=float),
                equal_nan=True,
            )
        else:
            same = before.astype(str).equals(after.astype(str))
        if not same:
            msg = f"Preexisting column '{column}' changed during the backfill"
            raise ValueError(msg)


def backfill(*, apply: bool, force: bool, season: int | None) -> dict[str, Any]:
    """Label every Gold lap file that lacks traffic exposure labels.

    Args:
        apply: Write the labelled frames back to disk. When ``False`` the run
            only reports what it would change.
        force: Recompute files that already carry the labels.
        season: Restrict the run to one season year.

    Returns:
        Summary counters for the run.

    Raises:
        ValueError: If a file fails verification.
    """
    settings = get_settings()
    outputs_dir = Path(settings.data_outputs_dir)
    files = sorted((outputs_dir / "laps").glob("season=*/round=*/race_laps.parquet"))
    if season is not None:
        files = [f for f in files if f"season={season}" in f.as_posix()]

    updated = skipped = laps = clean_laps = 0
    for index, path in enumerate(files, start=1):
        key = _parse_key(path)
        if key is None:
            logger.warning(
                "[%d/%d] Unrecognised path, skipping: %s", index, len(files), path
            )
            continue

        original = pd.read_parquet(path)
        present = [c for c in TRAFFIC_COLUMNS if c in original.columns]
        if present and not force:
            logger.info(
                "[%d/%d] %s already labelled (%s), skipping",
                index,
                len(files),
                path.name,
                ", ".join(present),
            )
            skipped += 1
            continue

        labelled = add_traffic_exposure(original)
        _verify(labelled, original)

        labelled_count = int(labelled["in_clean_air"].sum())
        laps += len(labelled)
        clean_laps += labelled_count
        logger.info(
            "[%d/%d] %s %s R%02d | %d laps | %d clean-air (%.1f%%)",
            index,
            len(files),
            "writing" if apply else "would write",
            key.year,
            key.round_number,
            len(labelled),
            labelled_count,
            100.0 * labelled_count / max(len(labelled), 1),
        )

        if apply:
            written = write_parquet(
                labelled, key, DataType.LAPS, base_dir=outputs_dir, overwrite=True
            )
            round_trip = pd.read_parquet(written)
            _verify(round_trip, original)
            if len(round_trip) != len(labelled):
                msg = f"Round-trip row count mismatch for {written}"
                raise ValueError(msg)
        updated += 1

    return {
        "files_seen": len(files),
        "files_labelled": updated,
        "files_skipped": skipped,
        "laps_labelled": laps,
        "clean_air_laps": clean_laps,
        "applied": apply,
    }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the labels back to disk (default: dry run)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute files that already carry the label columns",
    )
    parser.add_argument(
        "--season", type=int, default=None, help="Restrict to one season year"
    )
    return parser.parse_args()


if __name__ == "__main__":
    configure_root_pipeline_logger("INFO")
    args = parse_args()
    summary = backfill(apply=args.apply, force=args.force, season=args.season)
    logger.info("Traffic exposure backfill summary: %s", summary)
    print(f"\nBackfill {'applied' if summary['applied'] else 'dry run'}: {summary}")
