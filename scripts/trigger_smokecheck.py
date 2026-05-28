"""Lightweight Trigger.dev runtime smokecheck for the F1 pipeline."""

from __future__ import annotations

import importlib
import json
import platform
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_MODULES: tuple[str, ...] = (
    "f1_predictions.utils.config",
    "f1_predictions.utils.logging_setup",
    "f1_predictions.utils.race_detector",
    "f1_predictions.models",
    "f1_predictions.evaluation.post_race_verdict",
)

REQUIRED_FILES: tuple[Path, ...] = (
    Path("scripts/master_pipeline.py"),
    Path("data/external/track_metadata.csv"),
    Path("data/outputs/models/xgb_pace_model.joblib"),
)


@dataclass(frozen=True)
class CheckResult:
    """Result for one smokecheck assertion."""

    name: str
    success: bool
    detail: str


def check_required_file(project_root: Path, relative_path: Path) -> CheckResult:
    """Validate that a packaged runtime file exists and is non-empty.

    Args:
        project_root: Root directory of the Trigger worker checkout.
        relative_path: File path relative to ``project_root``.

    Returns:
        Check result with file status details.
    """
    file_path = project_root / relative_path
    if not file_path.is_file():
        return CheckResult(
            name=f"file:{relative_path.as_posix()}",
            success=False,
            detail=f"missing: {file_path}",
        )

    size_bytes = file_path.stat().st_size
    if size_bytes <= 0:
        return CheckResult(
            name=f"file:{relative_path.as_posix()}",
            success=False,
            detail=f"empty: {file_path}",
        )

    return CheckResult(
        name=f"file:{relative_path.as_posix()}",
        success=True,
        detail=f"{size_bytes} bytes",
    )


def check_import(module_name: str) -> CheckResult:
    """Validate that a required Python module imports in the worker runtime.

    Args:
        module_name: Dotted Python module path.

    Returns:
        Check result with import status details.
    """
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return CheckResult(
            name=f"import:{module_name}",
            success=False,
            detail=f"{type(exc).__name__}: {exc}",
        )

    module_file = getattr(module, "__file__", "built-in")
    return CheckResult(
        name=f"import:{module_name}",
        success=True,
        detail=str(module_file),
    )


def check_writable_directory(path: Path) -> CheckResult:
    """Validate that a runtime directory is writable.

    Args:
        path: Directory to create and write a temporary probe file into.

    Returns:
        Check result with write status details.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / ".trigger_smokecheck"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
    except Exception as exc:
        return CheckResult(
            name=f"writable:{path}",
            success=False,
            detail=f"{type(exc).__name__}: {exc}",
        )

    return CheckResult(name=f"writable:{path}", success=True, detail="ok")


def collect_checks(project_root: Path) -> list[CheckResult]:
    """Collect all Trigger runtime smokecheck results.

    Args:
        project_root: Root directory of the Trigger worker checkout.

    Returns:
        Ordered check results for required files, imports, and writable paths.
    """
    checks = [
        check_required_file(project_root, required_file)
        for required_file in REQUIRED_FILES
    ]
    checks.extend(check_import(module_name) for module_name in REQUIRED_MODULES)

    try:
        from f1_predictions.utils.config import get_settings

        settings = get_settings()
        writable_paths = (
            settings.fastf1_cache_dir,
            settings.reports_dir,
            project_root / "logs",
        )
        checks.extend(check_writable_directory(path) for path in writable_paths)
    except Exception as exc:
        checks.append(
            CheckResult(
                name="settings:writable_paths",
                success=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        )

    return checks


def build_payload(project_root: Path, checks: Iterable[CheckResult]) -> dict[str, Any]:
    """Build the compact JSON payload emitted to Trigger stdout.

    Args:
        project_root: Root directory of the Trigger worker checkout.
        checks: Smokecheck results.

    Returns:
        JSON-serializable smokecheck payload.
    """
    check_list = list(checks)
    return {
        "success": all(check.success for check in check_list),
        "python": platform.python_version(),
        "working_directory": str(project_root),
        "checks": [asdict(check) for check in check_list],
    }


def main() -> int:
    """Run the Trigger runtime smokecheck.

    Returns:
        Process exit code: 0 when all checks pass, otherwise 1.
    """
    project_root = Path.cwd()
    checks = collect_checks(project_root)
    payload = build_payload(project_root, checks)
    print(json.dumps(payload, separators=(",", ":")))

    if payload["success"]:
        return 0

    failed_checks = [check for check in checks if not check.success]
    for check in failed_checks:
        print(f"{check.name}: {check.detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
