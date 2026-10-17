"""Unit tests for the dashboard data publisher."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from f1_predictions.utils.dashboard_publish import (
    build_dashboard_manifest,
    collect_dashboard_files,
    discover_rounds,
    publish_dashboard_data,
)


class _FakeS3:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> None:
        self.puts.append(kwargs)

    @property
    def keys(self) -> list[str]:
        return [str(p["Key"]) for p in self.puts]


def _seed_season(reports_dir: Path, season: int = 2026) -> Path:
    """Create a realistic reports/<season> tree for a season."""
    season_dir = reports_dir / str(season)
    (season_dir / "summaries").mkdir(parents=True)
    (season_dir / "British_Grand_Prix" / "results").mkdir(parents=True)

    (season_dir / "calendar.json").write_text('{"season": 2026, "races": []}')
    (season_dir / "summaries" / "report_round_11.md").write_text("# Report 11")
    (season_dir / "summaries" / "predicted_report_round_12.md").write_text("# P12")
    (season_dir / "summaries" / "tyre_intelligence_round_11.json").write_text("{}")
    (season_dir / "British_Grand_Prix" / "results" / "predictions.csv").write_text(
        "Driver,predicted_laptime_xgb_s\nVER,88.1\n"
    )
    # Cruft that must never be published.
    (season_dir / ".DS_Store").write_bytes(b"\x00")
    (season_dir / "summaries" / "scratch.bin").write_bytes(b"\x00")
    return season_dir


def test_collect_dashboard_files_filters_and_sorts(tmp_path: Path) -> None:
    """Only allow-listed artifacts are collected, sorted, cruft excluded."""
    _seed_season(tmp_path)

    files = collect_dashboard_files(tmp_path, 2026)
    names = [f.name for f in files]

    assert "calendar.json" in names
    assert "predictions.csv" in names
    assert "report_round_11.md" in names
    assert ".DS_Store" not in names
    assert "scratch.bin" not in names
    assert files == sorted(files)


def test_collect_dashboard_files_empty_when_absent(tmp_path: Path) -> None:
    """A missing season directory yields no files (no crash)."""
    assert collect_dashboard_files(tmp_path, 2030) == []


def test_discover_rounds_from_filenames(tmp_path: Path) -> None:
    """Rounds are inferred from round_<N> in artifact names."""
    files = collect_dashboard_files(_seed_season(tmp_path).parent, 2026)
    assert discover_rounds(files) == [11, 12]


def test_build_dashboard_manifest_fields(tmp_path: Path) -> None:
    """Manifest carries season, prefix, rounds and relative file paths."""
    _seed_season(tmp_path)

    manifest = build_dashboard_manifest(tmp_path, 2026)

    assert manifest["season"] == 2026
    assert manifest["object_prefix"] == "dashboard/2026"
    assert manifest["rounds"] == [11, 12]
    assert manifest["file_count"] == len(manifest["files"])
    assert "calendar.json" in manifest["files"]
    assert "British_Grand_Prix/results/predictions.csv" in manifest["files"]
    assert all(not f.startswith("/") for f in manifest["files"])


def test_manifest_rounds_include_prediction_only_rounds(tmp_path: Path) -> None:
    """A round whose only artifact is results/predictions.csv still counts.

    That file name carries no ``round_N``, so without the calendar mapping the
    manifest would deny a round the dashboard happily renders — the mismatch
    that appears when a pre-race prediction is published with no results yet.
    """
    season_dir = tmp_path / "2026"
    (season_dir / "British_Grand_Prix" / "results").mkdir(parents=True)
    (season_dir / "British_Grand_Prix" / "results" / "predictions.csv").write_text(
        "Driver,predicted_laptime_xgb_s\nVER,88.1\n"
    )

    manifest = build_dashboard_manifest(
        tmp_path, 2026, directory_rounds={"British_Grand_Prix": 9}
    )

    assert manifest["rounds"] == [9]


def test_manifest_rounds_ignore_directories_the_calendar_does_not_know(
    tmp_path: Path,
) -> None:
    """A stray predictions.csv must not invent a round."""
    season_dir = tmp_path / "2026"
    (season_dir / "Nowhere_Grand_Prix" / "results").mkdir(parents=True)
    (season_dir / "Nowhere_Grand_Prix" / "results" / "predictions.csv").write_text(
        "Driver\n"
    )

    manifest = build_dashboard_manifest(
        tmp_path, 2026, directory_rounds={"British_Grand_Prix": 9}
    )

    assert manifest["rounds"] == []


def test_publish_manifest_rounds_use_the_calendar(tmp_path: Path) -> None:
    """publish_dashboard_data resolves prediction-only rounds via calendar.json."""
    season_dir = tmp_path / "2026"
    (season_dir / "United_States_Grand_Prix" / "results").mkdir(parents=True)
    (
        season_dir / "United_States_Grand_Prix" / "results" / "predictions.csv"
    ).write_text("Driver,RoundNumber\nNOR,18\n")
    (season_dir / "calendar.json").write_text(
        json.dumps(
            {
                "season": 2026,
                "races": [
                    {
                        "round": 18,
                        "name": "United States Grand Prix",
                        "dir": "United_States_Grand_Prix",
                        "date": "2026-10-25",
                    }
                ],
            }
        )
    )
    client = _FakeS3()

    publish_dashboard_data(tmp_path, 2026, bucket_name="b", client=client)

    body = next(
        payload["Body"]
        for payload in client.puts
        if str(payload["Key"]).endswith("manifest.json")
    )
    assert json.loads(body)["rounds"] == [18]


def test_publish_uploads_artifacts_and_manifest(tmp_path: Path) -> None:
    """Every artifact plus the manifest is uploaded under the season prefix."""
    _seed_season(tmp_path)
    client = _FakeS3()

    summary = publish_dashboard_data(tmp_path, 2026, bucket_name="b", client=client)

    assert summary["published"] == 5
    assert "dashboard/2026/manifest.json" in client.keys
    assert "dashboard/2026/calendar.json" in client.keys
    assert "dashboard/2026/British_Grand_Prix/results/predictions.csv" in client.keys

    # Manifest is uploaded LAST so its presence signals a complete bundle.
    assert client.keys[-1] == "dashboard/2026/manifest.json"
    manifest_body = json.loads(
        client.puts[-1]["Body"]  # type: ignore[arg-type]
    )
    assert manifest_body["season"] == 2026

    # Content types are inferred per artifact.
    csv_obj = next(p for p in client.puts if str(p["Key"]).endswith("predictions.csv"))
    assert csv_obj["ContentType"] == "text/csv"


def test_publish_respects_custom_prefix(tmp_path: Path) -> None:
    """A custom object prefix is honoured for every key."""
    _seed_season(tmp_path)
    client = _FakeS3()

    publish_dashboard_data(
        tmp_path, 2026, bucket_name="b", prefix="site", client=client
    )

    assert all(key.startswith("site/2026/") for key in client.keys)


def test_publish_returns_zero_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty season publishes nothing and needs no credentials."""
    monkeypatch.delenv("SUPABASE_S3_BUCKET_NAME", raising=False)

    summary = publish_dashboard_data(tmp_path, 2030, client=_FakeS3())

    assert summary["published"] == 0
    assert summary["files"] == []


def test_publish_raises_without_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publishing real data without a bucket is a hard configuration error."""
    _seed_season(tmp_path)
    monkeypatch.delenv("SUPABASE_S3_BUCKET_NAME", raising=False)

    with pytest.raises(ValueError, match="SUPABASE_S3_BUCKET_NAME"):
        publish_dashboard_data(tmp_path, 2026, client=_FakeS3())


def test_publish_falls_back_to_env_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bucket can come from the environment instead of an argument."""
    _seed_season(tmp_path)
    monkeypatch.setenv("SUPABASE_S3_BUCKET_NAME", "env-bucket")
    client = _FakeS3()

    publish_dashboard_data(tmp_path, 2026, client=client)

    assert all(p["Bucket"] == "env-bucket" for p in client.puts)
