"""Tests for the Trigger.dev runtime smokecheck."""

from pathlib import Path

from scripts.trigger_smokecheck import (
    build_payload,
    check_import,
    check_required_file,
    check_writable_directory,
)


def test_check_required_file_accepts_non_empty_file(tmp_path: Path) -> None:
    """A required file passes when it exists and has content."""
    relative_path = Path("data/external/track_metadata.csv")
    target_path = tmp_path / relative_path
    target_path.parent.mkdir(parents=True)
    target_path.write_text("EventName,TrackType\nMiami Grand Prix,Street\n")

    result = check_required_file(tmp_path, relative_path)

    assert result.success is True
    assert result.name == "file:data/external/track_metadata.csv"
    assert "bytes" in result.detail


def test_check_required_file_rejects_missing_file(tmp_path: Path) -> None:
    """A required file fails when it is absent from the runtime artifact."""
    result = check_required_file(tmp_path, Path("scripts/master_pipeline.py"))

    assert result.success is False
    assert result.name == "file:scripts/master_pipeline.py"
    assert "missing" in result.detail


def test_check_import_reports_importable_module() -> None:
    """A required module passes when it can be imported."""
    result = check_import("f1_predictions.utils.config")

    assert result.success is True
    assert result.name == "import:f1_predictions.utils.config"
    assert "config.py" in result.detail


def test_check_writable_directory_creates_and_cleans_probe(tmp_path: Path) -> None:
    """A writable directory passes and does not leave the probe file behind."""
    target_dir = tmp_path / "logs"

    result = check_writable_directory(target_dir)

    assert result.success is True
    assert target_dir.is_dir()
    assert not (target_dir / ".trigger_smokecheck").exists()


def test_build_payload_marks_failure_when_any_check_fails(tmp_path: Path) -> None:
    """The JSON payload reports failure if at least one check failed."""
    checks = [
        check_required_file(tmp_path, Path("missing.py")),
        check_writable_directory(tmp_path / "logs"),
    ]

    payload = build_payload(tmp_path, checks)

    assert payload["success"] is False
    assert payload["working_directory"] == str(tmp_path)
    assert len(payload["checks"]) == 2
