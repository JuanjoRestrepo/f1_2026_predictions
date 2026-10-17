"""Unit tests for scripts/validate_bundle.py.

The validator replaces a CI check that was silently a no-op, so its job is to
fail loudly on exactly the mistakes that used to reach ``databricks bundle
deploy``. Each test below pins one of those failure modes.

The last test runs the validator against this repository's own bundle, so the
real bundle can never silently drift out of structural validity.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.validate_bundle import Report, main, validate

REPO_ROOT = Path(__file__).resolve().parents[2]

_DATABRICKS_YML = """\
bundle:
  name: demo_bundle

include:
  - resources/*.yml

variables:
  catalog:
    default: main

targets:
  dev:
    default: true
"""

_JOBS_YML = """\
resources:
  jobs:
    demo_job:
      environments:
        - environment_key: serverless_py312
          spec:
            client: "2"
      tasks:
        - task_key: ingest
          environment_key: serverless_py312
          spark_python_task:
            python_file: ../entrypoint.py
        - task_key: transform
          depends_on:
            - task_key: ingest
          pipeline_task:
            pipeline_id: ${resources.pipelines.medallion.id}
"""

_PIPELINES_YML = """\
resources:
  pipelines:
    medallion:
      catalog: ${var.catalog}
      libraries:
        - notebook:
            path: ../src/pipeline.py
"""


def _valid_bundle() -> dict[str, str]:
    """Return the files of a minimal, structurally valid bundle."""
    return {
        "databricks.yml": _DATABRICKS_YML,
        "resources/jobs.yml": _JOBS_YML,
        "resources/pipelines.yml": _PIPELINES_YML,
        "entrypoint.py": "",
        "src/pipeline.py": "",
    }


def _write(root: Path, files: Mapping[str, str]) -> None:
    """Materialise a bundle tree under ``root``."""
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def _bundle(tmp_path: Path, overrides: Mapping[str, str] | None = None) -> Path:
    """Write the valid bundle with ``overrides`` applied and return its root."""
    files = _valid_bundle()
    files.update(overrides or {})
    _write(tmp_path, files)
    return tmp_path


def _messages(report: Report) -> str:
    """Flatten every problem into one string for substring assertions."""
    return "\n".join(str(problem) for problem in report.problems)


def test_valid_bundle_reports_no_problems(tmp_path: Path) -> None:
    """A well-formed bundle validates cleanly and counts its parts."""
    report = validate(_bundle(tmp_path))

    assert report.ok, _messages(report)
    assert report.jobs == 1
    assert report.tasks == 2
    assert report.resource_counts == {"jobs": 1, "pipelines": 1}


def test_missing_bundle_root_is_reported(tmp_path: Path) -> None:
    """A missing databricks.yml is a problem, not a crash."""
    report = validate(tmp_path)

    assert not report.ok
    assert "bundle root file not found" in _messages(report)


def test_unparsable_yaml_is_reported(tmp_path: Path) -> None:
    """A YAML syntax error names the offending file."""
    root = _bundle(tmp_path, {"resources/jobs.yml": "resources: [unclosed\n"})

    report = validate(root)

    assert not report.ok
    assert "resources/jobs.yml: YAML does not parse" in _messages(report)


def test_include_glob_matching_nothing_is_reported(tmp_path: Path) -> None:
    """An include spelled wrongly would otherwise deploy an empty bundle."""
    root = _bundle(tmp_path, {"databricks.yml": _DATABRICKS_YML.replace("resources/*.yml", "resource/*.yml")})

    report = validate(root)

    assert not report.ok
    assert "include 'resource/*.yml' matched no files" in _messages(report)


def test_missing_python_file_is_reported(tmp_path: Path) -> None:
    """A task pointing at a file that is not in the bundle fails."""
    root = _bundle(tmp_path, {"resources/jobs.yml": _JOBS_YML.replace("../entrypoint.py", "../nope.py")})

    report = validate(root)

    assert not report.ok
    assert "points at '../nope.py', which does not exist" in _messages(report)


def test_missing_library_file_is_reported(tmp_path: Path) -> None:
    """A pipeline library pointing at a missing notebook fails."""
    root = _bundle(tmp_path, {"resources/pipelines.yml": _PIPELINES_YML.replace("pipeline.py", "gone.py")})

    report = validate(root)

    assert not report.ok
    assert "'../src/gone.py', which does not exist" in _messages(report)


def test_undefined_variable_is_reported(tmp_path: Path) -> None:
    """A ${var.x} the bundle never declares fails."""
    root = _bundle(tmp_path, {"resources/pipelines.yml": _PIPELINES_YML.replace("${var.catalog}", "${var.missing}")})

    report = validate(root)

    assert not report.ok
    assert "${var.missing} is not declared under variables" in _messages(report)


def test_unresolved_resource_reference_is_reported(tmp_path: Path) -> None:
    """Cross-resource references must name something the bundle defines."""
    root = _bundle(
        tmp_path,
        {"resources/jobs.yml": _JOBS_YML.replace("${resources.pipelines.medallion.id}", "${resources.pipelines.ghost.id}")},
    )

    report = validate(root)

    assert not report.ok
    assert "${resources.pipelines.ghost...} does not resolve" in _messages(report)


def test_unknown_environment_key_is_reported(tmp_path: Path) -> None:
    """The serverless environment_key is the workspace's hard requirement."""
    jobs = _JOBS_YML.replace(
        "- task_key: ingest\n          environment_key: serverless_py312",
        "- task_key: ingest\n          environment_key: classic_py312",
    )
    root = _bundle(tmp_path, {"resources/jobs.yml": jobs})

    report = validate(root)

    assert not report.ok
    assert "environment_key 'classic_py312' is not declared" in _messages(report)


def test_unknown_dependency_is_reported(tmp_path: Path) -> None:
    """A depends_on naming no task in the job fails."""
    root = _bundle(tmp_path, {"resources/jobs.yml": _JOBS_YML.replace("- task_key: ingest\n          pipeline_task", "- task_key: ghost\n          pipeline_task")})

    report = validate(root)

    assert not report.ok
    assert "'ghost' is not a task in this job" in _messages(report)


def test_forward_dependency_is_allowed(tmp_path: Path) -> None:
    """A task may depend on one declared later in the list."""
    jobs = _JOBS_YML.replace("- task_key: ingest\n", "- task_key: transform2\n", 1)
    jobs = jobs.replace("- task_key: transform\n", "- task_key: ingest\n")
    root = _bundle(tmp_path, {"resources/jobs.yml": jobs})

    report = validate(root)

    assert report.ok, _messages(report)


def test_duplicate_task_key_is_reported(tmp_path: Path) -> None:
    """Two tasks sharing a task_key fail."""
    root = _bundle(tmp_path, {"resources/jobs.yml": _JOBS_YML.replace("- task_key: transform", "- task_key: ingest")})

    report = validate(root)

    assert not report.ok
    assert "duplicate task_key 'ingest'" in _messages(report)


def test_task_without_a_type_is_reported(tmp_path: Path) -> None:
    """A task with no recognisable task type fails."""
    root = _bundle(
        tmp_path,
        {
            "resources/jobs.yml": _JOBS_YML.replace(
                "spark_python_task:\n            python_file: ../entrypoint.py",
                "description: nothing to run",
            )
        },
    )

    report = validate(root)

    assert not report.ok
    assert "task declares no task type" in _messages(report)


def test_task_with_two_types_is_reported(tmp_path: Path) -> None:
    """A task with two task types fails, as DABs requires exactly one."""
    root = _bundle(
        tmp_path,
        {
            "resources/jobs.yml": _JOBS_YML.replace(
                "spark_python_task:\n            python_file: ../entrypoint.py",
                "spark_python_task:\n            python_file: ../entrypoint.py\n          notebook_task:\n            notebook_path: ../src/pipeline.py",
            )
        },
    )

    report = validate(root)

    assert not report.ok
    assert "DABs allows exactly one" in _messages(report)


def test_unknown_resource_type_is_reported(tmp_path: Path) -> None:
    """A singular/plural typo under resources: is caught."""
    root = _bundle(tmp_path, {"resources/pipelines.yml": _PIPELINES_YML.replace("pipelines:", "pipeline:")})

    report = validate(root)

    assert not report.ok
    assert "unknown resource type 'pipeline'" in _messages(report)


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits 0 on success and 1 with a printed report on failure."""
    good = _bundle(tmp_path / "good")

    assert main(["--root", str(good)]) == 0
    assert "Bundle structure OK" in capsys.readouterr().out

    bad = _bundle(tmp_path / "bad", {"databricks.yml": "include:\n  - resources/*.yml\n"})

    assert main(["--root", str(bad)]) == 1
    captured = capsys.readouterr().out
    assert "Bundle validation FAILED" in captured
    assert "bundle.name is required" in captured


def test_repository_bundle_is_valid() -> None:
    """This repository's own bundle must always pass the offline checks."""
    report = validate(REPO_ROOT)

    assert report.ok, _messages(report)
    assert report.resource_counts == {"jobs": 1, "pipelines": 1, "volumes": 1}
    assert report.tasks == 5
