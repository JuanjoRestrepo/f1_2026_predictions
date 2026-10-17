"""Unit tests for scripts/rotate_supabase_s3_keys.py.

The rotation helper is the only code path that writes S3 credentials, so its two
riskiest behaviours are pinned here:

* ``rewrite_lines`` must edit the dotenv file surgically — comments, ordering and
  unrelated settings survive untouched, and a file without a trailing newline
  must not get its last line glued to an appended key.
* Secret values must never reach a log or an argument vector. They are handed to
  the Databricks CLI on stdin, and ``mask`` is what ends up in stdout.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.rotate_supabase_s3_keys import (
    ACCESS_KEY,
    BUCKET_KEY,
    ENDPOINT_KEY,
    SECRET_KEY,
    main,
    parse_env,
    rewrite_lines,
    set_databricks_secret,
    validate,
    write_env,
)

_ENDPOINT = "https://example.supabase.co/storage/v1/s3"
_ENV_BODY = (
    "# comment survives\n"
    f"{ENDPOINT_KEY}={_ENDPOINT}\n"
    f"{ACCESS_KEY}=oldid\n"
    f"{SECRET_KEY}=oldsecret\n"
    f"{BUCKET_KEY}=f1-cache\n"
)


def _seed_env(tmp_path: Path, body: str = _ENV_BODY) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(body, encoding="utf-8")
    return env_path


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_parse_env_ignores_noise_and_strips_quotes(tmp_path: Path) -> None:
    """Comments and blank lines are skipped; quoting is removed."""
    env_path = _seed_env(
        tmp_path,
        "# c\n\nA=1\nB=\"two\"\nC='three'\nD=has=equals\nnot-a-pair\n",
    )

    assert parse_env(env_path) == {
        "A": "1",
        "B": "two",
        "C": "three",
        "D": "has=equals",
    }


def test_rewrite_lines_edits_in_place_and_preserves_everything_else() -> None:
    """Rotated keys are replaced where they stand; comments and order stay."""
    rendered, changed = rewrite_lines(
        _ENV_BODY, {ACCESS_KEY: "newid", SECRET_KEY: "newsecret"}
    )

    assert changed == [ACCESS_KEY, SECRET_KEY]
    assert rendered.startswith("# comment survives\n")
    assert rendered == (
        "# comment survives\n"
        f"{ENDPOINT_KEY}={_ENDPOINT}\n"
        f"{ACCESS_KEY}=newid\n"
        f"{SECRET_KEY}=newsecret\n"
        f"{BUCKET_KEY}=f1-cache\n"
    )


def test_rewrite_lines_appends_keys_that_are_absent() -> None:
    """A missing key is appended under an explanatory heading."""
    rendered, changed = rewrite_lines("A=1\n", {BUCKET_KEY: "f1-cache"})

    assert changed == [BUCKET_KEY]
    assert rendered == (
        f"A=1\n\n# Added by scripts/rotate_supabase_s3_keys.py\n{BUCKET_KEY}=f1-cache\n"
    )


def test_rewrite_lines_does_not_glue_onto_a_missing_final_newline() -> None:
    """A file ending mid-line still appends cleanly."""
    rendered, _ = rewrite_lines("A=1", {BUCKET_KEY: "f1-cache"})

    assert rendered.splitlines() == [
        "A=1",
        "",
        "# Added by scripts/rotate_supabase_s3_keys.py",
        f"{BUCKET_KEY}=f1-cache",
    ]


@pytest.mark.parametrize("value", ["", "has space", "has\ttab", "line\nbreak"])
def test_validate_rejects_values_that_would_corrupt_storage(value: str) -> None:
    """Empty or whitespace-bearing values are refused before anything is written."""
    with pytest.raises(SystemExit):
        validate(ACCESS_KEY, value)


# ---------------------------------------------------------------------------
# Disk and CLI boundaries
# ---------------------------------------------------------------------------


def test_write_env_backs_up_with_owner_only_permissions(tmp_path: Path) -> None:
    """The pre-rotation contents are preserved in a locked-down backup."""
    env_path = _seed_env(tmp_path)

    backup = write_env(env_path, f"{ACCESS_KEY}=newid\n")

    assert backup.name.startswith(".env.bak.")
    assert backup.read_text(encoding="utf-8") == _ENV_BODY
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


@patch("scripts.rotate_supabase_s3_keys.subprocess.run")
def test_set_databricks_secret_passes_the_value_on_stdin(mock_run: MagicMock) -> None:
    """The secret must travel on stdin, never in argv (process list / history)."""
    mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

    assert set_databricks_secret("f1_secrets", SECRET_KEY, "s3cr3t", dry_run=False)

    argv = mock_run.call_args.args[0]
    assert argv == ["databricks", "secrets", "put-secret", "f1_secrets", SECRET_KEY]
    assert mock_run.call_args.kwargs["input"] == "s3cr3t"
    assert not any("s3cr3t" in str(part) for part in argv)


@patch("scripts.rotate_supabase_s3_keys.subprocess.run")
def test_set_databricks_secret_reports_cli_failure(mock_run: MagicMock) -> None:
    """A non-zero exit is surfaced as False so the caller can abort."""
    mock_run.return_value = SimpleNamespace(
        returncode=1, stdout="", stderr="PERMISSION_DENIED"
    )

    assert not set_databricks_secret("f1_secrets", SECRET_KEY, "s3cr3t", dry_run=False)


@patch("scripts.rotate_supabase_s3_keys.subprocess.run")
def test_set_databricks_secret_prints_nothing(
    mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not the value, not a masked prefix, not even the variable name."""
    mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

    assert set_databricks_secret(
        "f1_secrets", SECRET_KEY, "s3cr3t-value", dry_run=False
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@patch("scripts.rotate_supabase_s3_keys.subprocess.run")
def test_set_databricks_secret_failure_prints_nothing(
    mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI's stderr can echo the command, so it is never forwarded."""
    mock_run.return_value = SimpleNamespace(
        returncode=1, stdout="", stderr="Error: put-secret SUPABASE_S3_SECRET_KEY"
    )

    assert not set_databricks_secret("f1_secrets", SECRET_KEY, "s3cr3t", dry_run=False)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@patch("scripts.rotate_supabase_s3_keys.subprocess.run")
def test_set_databricks_secret_dry_run_skips_the_cli(mock_run: MagicMock) -> None:
    """A dry run must not mutate the scope."""
    assert set_databricks_secret("f1_secrets", SECRET_KEY, "s3cr3t", dry_run=True)

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_never_prints_credential_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: the credential values must not appear in the output at all."""
    env_path = _seed_env(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rotate",
            "--env-file",
            str(env_path),
            "--access-key",
            "AKIAIOSFODNN7EXAMPLE",
            "--secret-key",
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "--skip-databricks",
            "--dry-run",
        ],
    )

    assert main() == 0
    out = capsys.readouterr().out

    for leaked in ("AKIAIOSFODNN7EXAMPLE", "AKIA", "wJalrXUtnFEMI", "wJal"):
        assert leaked not in out
    assert "<redacted>" in out


def test_main_dry_run_leaves_the_env_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run reports a plan without writing anything."""
    env_path = _seed_env(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rotate",
            "--env-file",
            str(env_path),
            "--access-key",
            "newid",
            "--secret-key",
            "newsecret",
            "--skip-databricks",
            "--dry-run",
        ],
    )

    assert main() == 0
    assert env_path.read_text(encoding="utf-8") == _ENV_BODY
    assert list(tmp_path.glob(".env.bak.*")) == []


def test_main_rotates_then_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real run rewrites the pair, keeps a backup, and verifies the new one."""
    env_path = _seed_env(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rotate",
            "--env-file",
            str(env_path),
            "--access-key",
            "newid",
            "--secret-key",
            "newsecret",
            "--skip-databricks",
        ],
    )

    with patch(
        "scripts.rotate_supabase_s3_keys.verify", return_value=True
    ) as mock_verify:
        assert main() == 0

    values = parse_env(env_path)
    assert values[ACCESS_KEY] == "newid"
    assert values[SECRET_KEY] == "newsecret"
    assert values[ENDPOINT_KEY] == _ENDPOINT
    assert values[BUCKET_KEY] == "f1-cache"
    assert len(list(tmp_path.glob(".env.bak.*"))) == 1
    mock_verify.assert_called_once_with(_ENDPOINT, "newid", "newsecret", "f1-cache")


def test_main_stops_when_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreachable bucket is reported as a failure, not a silent success."""
    env_path = _seed_env(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rotate",
            "--env-file",
            str(env_path),
            "--access-key",
            "newid",
            "--secret-key",
            "newsecret",
            "--skip-databricks",
        ],
    )

    with patch("scripts.rotate_supabase_s3_keys.verify", return_value=False):
        assert main() == 1


def test_main_requires_endpoint_and_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a known endpoint/bucket there is nothing safe to write."""
    env_path = _seed_env(tmp_path, body=f"{ACCESS_KEY}=oldid\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["rotate", "--env-file", str(env_path), "--skip-databricks", "--dry-run"],
    )

    assert main() == 1
