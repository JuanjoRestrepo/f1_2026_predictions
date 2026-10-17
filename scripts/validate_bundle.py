#!/usr/bin/env python
"""Offline structural validation of the Databricks Asset Bundle (DABs).

``databricks bundle validate`` is the authoritative check, but it requires a
workspace connection. CI therefore skipped it whenever no credentials were
configured — and because none ever were, the "Validate DABs Bundle" check was a
green tick that validated nothing, so the bundle was only ever checked at
``bundle deploy`` time.

This module decides everything that can be decided from the files alone. Each
check corresponds to a mistake that would otherwise surface at deploy time:

* YAML that does not parse.
* An ``include:`` glob that matches nothing, or a literal path that is missing.
* ``spark_python_task.python_file`` / ``notebook_task.notebook_path`` / library
  paths that do not exist on disk. They are resolved relative to the file that
  declares them, which is how DABs resolves them.
* A ``task.environment_key`` with no matching entry in the job's ``environments``
  (the serverless requirement for this workspace, so it is worth pinning).
* A ``depends_on.task_key`` that names no task in the job, or a duplicated
  ``task_key``.
* A task that declares no task type, or more than one.
* ``${var.x}`` and ``${resources.<type>.<name>...}`` substitutions that reference
  something the bundle never defines.
* An unknown key under ``resources:`` — usually a typo such as ``pipeline:``
  where ``pipelines:`` was meant.

The exit code is 0 when the bundle is structurally sound and 1 otherwise, so the
script is safe to use as a CI gate.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

BUNDLE_FILE = "databricks.yml"

# Resource types accepted under ``resources:``. A key outside this set is almost
# always a typo (``pipeline:`` for ``pipelines:``). Extend the set when DABs
# gains a resource type — the failure message says so.
KNOWN_RESOURCE_TYPES = frozenset(
    {
        "apps",
        "catalogs",
        "clusters",
        "dashboards",
        "database_catalogs",
        "database_instances",
        "experiments",
        "jobs",
        "knowledge_assistants",
        "model_serving_endpoints",
        "models",
        "pipelines",
        "quality_monitors",
        "registered_models",
        "schemas",
        "secret_scopes",
        "serving_endpoints",
        "sql_warehouses",
        "storage_credentials",
        "vector_search_endpoints",
        "vector_search_indexes",
        "volumes",
    }
)

# Every job task must declare exactly one of these.
TASK_TYPE_KEYS = (
    "condition_task",
    "dbt_task",
    "for_each_task",
    "notebook_task",
    "pipeline_task",
    "run_job_task",
    "spark_jar_task",
    "spark_python_task",
    "spark_submit_task",
    "sql_task",
)

# Keys whose string value points at a file that must exist inside the bundle.
FILE_KEYS = ("python_file", "notebook_path", "project_directory")

# Library entry keys that name a bundle file directly.
LIBRARY_FILE_KEYS = ("egg", "jar", "requirements", "whl")

_VAR_REF = re.compile(r"\$\{var\.([A-Za-z0-9_]+)\}")
_RESOURCE_REF = re.compile(r"\$\{resources\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")


@dataclass(frozen=True)
class Problem:
    """A single structural defect, tagged with where it was found."""

    where: str
    message: str

    def __str__(self) -> str:
        """Render as ``file: message`` for terminal output."""
        return f"{self.where}: {self.message}"


@dataclass
class Report:
    """Outcome of a validation run."""

    files: list[str] = field(default_factory=list)
    resource_counts: dict[str, int] = field(default_factory=dict)
    jobs: int = 0
    tasks: int = 0
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when no structural problem was found."""
        return not self.problems


def _rel(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when possible, else as given."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _load(path: Path, root: Path, report: Report) -> dict[str, Any] | None:
    """Parse one YAML file, recording a problem instead of raising."""
    where = _rel(path, root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.problems.append(Problem(where, f"cannot read file: {exc}"))
        return None
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        report.problems.append(Problem(where, f"YAML does not parse: {first_line}"))
        return None
    if document is None:
        return {}
    if not isinstance(document, dict):
        report.problems.append(Problem(where, "top level must be a mapping"))
        return None
    return document


def _iter_strings(node: Any) -> Iterator[str]:
    """Yield every string value nested inside ``node``."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)


def _iter_library(entry: Any, where: str) -> Iterator[tuple[str, str]]:
    """Yield the file references inside one ``libraries:`` list entry."""
    if not isinstance(entry, dict):
        return
    for kind, body in entry.items():
        if kind in LIBRARY_FILE_KEYS and isinstance(body, str):
            yield f"{where}.{kind}", body
        elif kind in ("file", "notebook") and isinstance(body, dict):
            path = body.get("path")
            if isinstance(path, str):
                yield f"{where}.{kind}.path", path


def _iter_file_refs(node: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(location, raw path)`` for every in-bundle file reference.

    Deliberately narrow: only the keys DABs treats as bundle files are matched,
    so a Unity Catalog path or an arbitrary ``path`` setting is never checked.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            if key in FILE_KEYS and isinstance(value, str):
                yield here, value
            elif key == "libraries" and isinstance(value, list):
                for index, entry in enumerate(value):
                    yield from _iter_library(entry, f"{here}[{index}]")
            else:
                yield from _iter_file_refs(value, here)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _iter_file_refs(item, f"{prefix}[{index}]")


def _check_task_types(task: dict[str, Any], where: str, report: Report) -> None:
    """Require exactly one task type, as DABs does."""
    present = sorted(key for key in TASK_TYPE_KEYS if key in task)
    if not present:
        report.problems.append(
            Problem(where, f"task declares no task type (expected one of {', '.join(TASK_TYPE_KEYS)})")
        )
    elif len(present) > 1:
        report.problems.append(
            Problem(where, f"task declares {len(present)} task types ({', '.join(present)}); DABs allows exactly one")
        )


def _check_job(name: str, job: Any, where: str, report: Report) -> None:
    """Validate one job's environments, task keys and dependencies."""
    report.jobs += 1
    if not isinstance(job, dict):
        report.problems.append(Problem(where, "job body must be a mapping"))
        return

    environment_keys: set[str] = set()
    environments = job.get("environments")
    if environments is not None and not isinstance(environments, list):
        report.problems.append(Problem(where, "environments must be a list"))
    for index, environment in enumerate(environments or []):
        entry_where = f"{where}.environments[{index}]"
        if not isinstance(environment, dict):
            report.problems.append(Problem(entry_where, "environment must be a mapping"))
            continue
        key = environment.get("environment_key")
        if not isinstance(key, str):
            report.problems.append(Problem(entry_where, "missing environment_key"))
            continue
        if key in environment_keys:
            report.problems.append(Problem(entry_where, f"duplicate environment_key '{key}'"))
        environment_keys.add(key)

    tasks = job.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        report.problems.append(Problem(where, "job must declare at least one task"))
        return

    # Pass 1: collect task keys so dependencies may point forwards.
    task_keys: list[str] = []
    for index, task in enumerate(tasks):
        report.tasks += 1
        key = task.get("task_key") if isinstance(task, dict) else None
        if not isinstance(key, str):
            report.problems.append(Problem(f"{where}.tasks[{index}]", "missing task_key"))
            continue
        if key in task_keys:
            report.problems.append(Problem(f"{where}.tasks[{key}]", f"duplicate task_key '{key}'"))
        task_keys.append(key)

    # Pass 2: per-task checks.
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            report.problems.append(Problem(f"{where}.tasks[{index}]", "task must be a mapping"))
            continue
        key = task.get("task_key")
        task_where = f"{where}.tasks.{key}" if isinstance(key, str) else f"{where}.tasks[{index}]"

        _check_task_types(task, task_where, report)

        environment_key = task.get("environment_key")
        if isinstance(environment_key, str) and environment_key not in environment_keys:
            report.problems.append(
                Problem(task_where, f"environment_key '{environment_key}' is not declared in this job's environments")
            )

        for dep_index, dependency in enumerate(task.get("depends_on") or []):
            dep_where = f"{task_where}.depends_on[{dep_index}]"
            dep_key = dependency.get("task_key") if isinstance(dependency, dict) else None
            if not isinstance(dep_key, str):
                report.problems.append(Problem(dep_where, "missing task_key"))
            elif dep_key not in task_keys:
                report.problems.append(Problem(dep_where, f"'{dep_key}' is not a task in this job"))


def validate(root: Path) -> Report:
    """Validate the bundle rooted at ``root`` and return a :class:`Report`."""
    report = Report()
    bundle_path = root / BUNDLE_FILE
    if not bundle_path.is_file():
        report.problems.append(Problem(BUNDLE_FILE, "bundle root file not found"))
        return report

    bundle_document = _load(bundle_path, root, report)
    if bundle_document is None:
        return report
    report.files.append(BUNDLE_FILE)
    documents: list[tuple[Path, dict[str, Any]]] = [(bundle_path, bundle_document)]

    bundle_block = bundle_document.get("bundle")
    name = bundle_block.get("name") if isinstance(bundle_block, dict) else None
    if not isinstance(name, str) or not name:
        report.problems.append(Problem(BUNDLE_FILE, "bundle.name is required"))

    includes = bundle_document.get("include")
    if includes is not None and not isinstance(includes, list):
        report.problems.append(Problem(BUNDLE_FILE, "include must be a list of paths"))
        includes = None
    for pattern in includes or []:
        if not isinstance(pattern, str):
            report.problems.append(Problem(BUNDLE_FILE, "include entries must be strings"))
            continue
        matches = sorted(candidate for candidate in root.glob(pattern) if candidate.is_file())
        if not matches:
            report.problems.append(Problem(BUNDLE_FILE, f"include '{pattern}' matched no files"))
        for match in matches:
            child = _load(match, root, report)
            if child is None:
                continue
            documents.append((match, child))
            report.files.append(_rel(match, root))

    # ── resources: collect, reject unknown types, catch duplicates ────────────
    resources: dict[str, dict[str, Any]] = {}
    for path, document in documents:
        where = _rel(path, root)
        declared = document.get("resources")
        if declared is None:
            continue
        if not isinstance(declared, dict):
            report.problems.append(Problem(where, "resources must be a mapping"))
            continue
        for resource_type, entries in declared.items():
            if resource_type not in KNOWN_RESOURCE_TYPES:
                report.problems.append(
                    Problem(
                        where,
                        f"unknown resource type '{resource_type}' — extend KNOWN_RESOURCE_TYPES if DABs added it",
                    )
                )
                continue
            if not isinstance(entries, dict):
                report.problems.append(Problem(where, f"resources.{resource_type} must map names to definitions"))
                continue
            bucket = resources.setdefault(resource_type, {})
            for resource_name, body in entries.items():
                if resource_name in bucket:
                    report.problems.append(
                        Problem(where, f"resources.{resource_type}.{resource_name} is defined more than once")
                    )
                bucket[resource_name] = body

    report.resource_counts = {resource_type: len(entries) for resource_type, entries in sorted(resources.items())}

    variables = bundle_document.get("variables")
    variable_names = set(variables) if isinstance(variables, dict) else set()

    # ── substitutions ────────────────────────────────────────────────────────
    for path, document in documents:
        where = _rel(path, root)
        for text in _iter_strings(document):
            for match in _VAR_REF.finditer(text):
                if match.group(1) not in variable_names:
                    report.problems.append(Problem(where, f"${{var.{match.group(1)}}} is not declared under variables"))
            for match in _RESOURCE_REF.finditer(text):
                resource_type, resource_name = match.groups()
                if resource_name not in resources.get(resource_type, {}):
                    report.problems.append(
                        Problem(where, f"${{resources.{resource_type}.{resource_name}...}} does not resolve")
                    )

    # ── in-bundle file references ────────────────────────────────────────────
    for path, document in documents:
        where = _rel(path, root)
        for location, raw in _iter_file_refs(document):
            if raw.startswith("/"):
                continue  # workspace-absolute path, not a bundle file
            if not (path.parent / raw).is_file():
                report.problems.append(Problem(where, f"{location} points at '{raw}', which does not exist"))

    # ── jobs ─────────────────────────────────────────────────────────────────
    for job_name, job in resources.get("jobs", {}).items():
        _check_job(job_name, job, f"resources.jobs.{job_name}", report)

    # Collapse identical findings: a repeated substitution in one file would
    # otherwise be reported once per occurrence.
    seen: set[tuple[str, str]] = set()
    unique: list[Problem] = []
    for problem in report.problems:
        key = (problem.where, problem.message)
        if key not in seen:
            seen.add(key)
            unique.append(problem)
    report.problems = unique

    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validation and return a process exit code."""
    parser = argparse.ArgumentParser(
        description="Validate the Databricks bundle structure without a workspace connection.",
    )
    parser.add_argument("--root", default=".", help="Bundle root directory (default: current directory).")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = validate(root)

    if not report.ok:
        print(f"Bundle validation FAILED — {len(report.problems)} problem(s) under {root}:")
        for problem in report.problems:
            print(f"  {problem}")
        return 1

    def describe(resource_type: str, count: int) -> str:
        """Render ``1 pipelines`` as ``1 pipeline`` (every DABs type is plural)."""
        label = resource_type[:-1] if count == 1 and resource_type.endswith("s") else resource_type
        return f"{count} {label}"

    counts = ", ".join(describe(resource_type, count) for resource_type, count in report.resource_counts.items())
    task_label = "task" if report.tasks == 1 else "tasks"
    print(f"Bundle structure OK — {len(report.files)} file(s), {counts or 'no resources'}, {report.tasks} {task_label}")
    print("Run 'databricks bundle validate --target dev' for the authoritative workspace check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
