"""Unit tests for the in-Databricks report bundle builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_predictions.databricks import report_bundle


def _make_round(season_dir: Path, round_number: int) -> None:
    """Write the one artifact that marks a round as reported."""
    summaries = season_dir / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / f"actual_results_round_{round_number}.json").write_text(
        '{"results": []}'
    )


def _no_bucket(*_: object, **__: object) -> dict[str, object]:
    """Stand-in for an unconfigured object store."""
    msg = "no bucket"
    raise ValueError(msg)


def test_seed_prefers_the_volume(tmp_path: Path) -> None:
    """A previous cloud build wins over the repository tree."""
    bundle = tmp_path / "bundle"
    project_root = tmp_path / "project"
    _make_round(bundle / "2026", 20)
    _make_round(project_root / "reports" / "2026", 19)

    reports_dir = tmp_path / "staging" / "reports"
    season_dir = report_bundle._seed_reports(2026, bundle, project_root, reports_dir)

    assert (season_dir / "summaries" / "actual_results_round_20.json").exists()
    assert not (season_dir / "summaries" / "actual_results_round_19.json").exists()


def test_seed_falls_back_to_object_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a Volume, the currently published bundle seeds the build."""
    bundle = tmp_path / "bundle"
    project_root = tmp_path / "project"
    _make_round(project_root / "reports" / "2026", 19)
    reports_dir = tmp_path / "staging" / "reports"

    def fake_download(destination: Path, season: int, **_: object) -> dict[str, object]:
        _make_round(destination / str(season), 21)
        return {"downloaded": 1, "season": season, "source": "s3://b/2026/"}

    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        fake_download,
    )

    season_dir = report_bundle._seed_reports(2026, bundle, project_root, reports_dir)

    assert (season_dir / "summaries" / "actual_results_round_21.json").exists()
    assert not (season_dir / "summaries" / "actual_results_round_19.json").exists()


def test_seed_falls_back_to_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh workspace with no bucket still starts from the committed tree."""
    bundle = tmp_path / "bundle"
    project_root = tmp_path / "project"
    _make_round(project_root / "reports" / "2026", 18)
    reports_dir = tmp_path / "staging" / "reports"

    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        _no_bucket,
    )

    season_dir = report_bundle._seed_reports(2026, bundle, project_root, reports_dir)

    assert (season_dir / "summaries" / "actual_results_round_18.json").exists()


def test_generate_skips_a_round_already_in_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An already-reported round is not regenerated on the next scheduled run."""
    bundle = tmp_path / "bundle"
    _make_round(bundle / "2026", 21)
    monkeypatch.setattr(report_bundle, "volume_bundle_root", lambda *_: bundle)
    monkeypatch.setattr(report_bundle, "_staging_root", lambda: tmp_path / "staging")

    def fail_if_called() -> None:
        msg = "pipeline must not run"
        raise AssertionError(msg)

    monkeypatch.setattr("scripts.master_pipeline.main", fail_if_called)

    summary = report_bundle.generate_report_bundle(
        season=2026,
        catalog="main",
        schema="prod",
        project_root=tmp_path,
        round_number=21,
    )

    assert summary["generated"] is False
    assert summary["reason"] == "already-present"


def test_generate_syncs_the_season_to_the_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated season tree is copied to the bundle Volume."""
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(report_bundle, "volume_bundle_root", lambda *_: bundle)
    monkeypatch.setattr(report_bundle, "_staging_root", lambda: tmp_path / "staging")
    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        _no_bucket,
    )

    def fake_main() -> None:
        from scripts import master_pipeline

        _make_round(Path(master_pipeline.REPORTS_BASE) / "2026", 21)

    monkeypatch.setattr("scripts.master_pipeline.main", fake_main)

    summary = report_bundle.generate_report_bundle(
        season=2026,
        catalog="main",
        schema="prod",
        project_root=tmp_path,
        round_number=21,
    )

    assert summary["generated"] is True
    assert (bundle / "2026" / "summaries" / "actual_results_round_21.json").exists()


def test_generate_preserves_existing_narratives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A derived-chart refresh must not replace good Gemini copy with fallback."""
    bundle = tmp_path / "bundle"
    season = bundle / "2026"
    _make_round(season, 21)
    summaries = season / "summaries"
    (summaries / "report_round_21.md").write_text("KEEP ACTUAL", encoding="utf-8")
    (summaries / "predicted_report_round_21.md").write_text(
        "KEEP PREDICTED", encoding="utf-8"
    )
    monkeypatch.setattr(report_bundle, "volume_bundle_root", lambda *_: bundle)
    monkeypatch.setattr(report_bundle, "_staging_root", lambda: tmp_path / "staging")
    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        _no_bucket,
    )

    def fake_main() -> None:
        from scripts import master_pipeline

        base = Path(master_pipeline.REPORTS_BASE) / "2026"
        _make_round(base, 21)
        (base / "summaries" / "report_round_21.md").write_text(
            "FALLBACK", encoding="utf-8"
        )
        (base / "summaries" / "predicted_report_round_21.md").write_text(
            "FALLBACK", encoding="utf-8"
        )

    monkeypatch.setattr("scripts.master_pipeline.main", fake_main)

    report_bundle.generate_report_bundle(
        season=2026,
        catalog="main",
        schema="prod",
        project_root=tmp_path,
        round_number=21,
        force=True,
        preserve_narratives=True,
    )

    published = bundle / "2026" / "summaries"
    assert (published / "report_round_21.md").read_text(encoding="utf-8") == "KEEP ACTUAL"
    assert (
        published / "predicted_report_round_21.md"
    ).read_text(encoding="utf-8") == "KEEP PREDICTED"


def test_generate_raises_when_no_actual_results_are_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A silent pipeline failure must not publish an incomplete bundle."""
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(report_bundle, "volume_bundle_root", lambda *_: bundle)
    monkeypatch.setattr(report_bundle, "_staging_root", lambda: tmp_path / "staging")
    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        _no_bucket,
    )
    monkeypatch.setattr("scripts.master_pipeline.main", lambda: None)

    with pytest.raises(RuntimeError, match="without"):
        report_bundle.generate_report_bundle(
            season=2026,
            catalog="main",
            schema="prod",
            project_root=tmp_path,
            round_number=21,
        )

    assert not (bundle / "2026").exists()


def test_generate_prerace_uses_upcoming_round_and_predicted_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-race mode resolves the upcoming round and verifies predicted artifacts."""
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(report_bundle, "volume_bundle_root", lambda *_: bundle)
    monkeypatch.setattr(report_bundle, "_staging_root", lambda: tmp_path / "staging")
    monkeypatch.setattr(
        "f1_predictions.utils.dashboard_publish.download_dashboard_bundle",
        _no_bucket,
    )
    monkeypatch.setattr(
        "f1_predictions.utils.race_detector.detect_upcoming_race",
        lambda season, days_ahead=4: {"round": 22, "name": "Qatar Grand Prix"},
    )

    def fake_main() -> None:
        from scripts import master_pipeline

        summaries = Path(master_pipeline.REPORTS_BASE) / "2026" / "summaries"
        summaries.mkdir(parents=True, exist_ok=True)
        (summaries / "predicted_lap_positions_round_22.json").write_text(
            '{"drivers": []}', encoding="utf-8"
        )
        (summaries / "predicted_report_round_22.md").write_text(
            "# Qatar Preview", encoding="utf-8"
        )

    monkeypatch.setattr("scripts.master_pipeline.main", fake_main)

    summary = report_bundle.generate_report_bundle(
        season=2026,
        catalog="main",
        schema="prod",
        project_root=tmp_path,
        phase="pre-race",
    )

    assert summary["generated"] is True
    assert summary["round"] == 22
    assert summary["phase"] == "pre-race"
    assert (
        bundle / "2026" / "summaries" / "predicted_lap_positions_round_22.json"
    ).exists()
