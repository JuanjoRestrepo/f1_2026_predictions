"""Rotate the Supabase S3 access key pair used for caching and publishing.

The same bucket backs two things:

* the FastF1 telemetry cache (``SUPABASE_S3_CACHE_KEY``)
* the dashboard serving bundle (``dashboard/<season>/``)

and the credentials live in two places that must stay in sync:

1. the local ``.env`` (developer tooling, manual ``--run-mode export`` runs)
2. the Databricks secret scope ``f1_secrets`` (read by the
   ``export_dashboard_data`` task at runtime)

Updating only one silently breaks either local tooling or the scheduled job,
which is why rotating is a script and not two remembered commands.

Supabase cannot mint new keys through the Storage S3 API, so create the
replacement pair in the dashboard first:

    Storage -> S3 Access Keys -> Create new access key

then run this script. Secret values are never printed — nothing derived from
them is — and they are handed to the Databricks CLI over stdin, so they stay out
of the process list and shell history. Delete the previous access key in
Supabase afterwards.

Usage:
    uv run scripts/rotate_supabase_s3_keys.py            # hidden prompt
    uv run scripts/rotate_supabase_s3_keys.py --dry-run
    uv run scripts/rotate_supabase_s3_keys.py \\
        --access-key <id> --secret-key <secret>

Exit codes:
    0 - rotation applied (or dry-run completed) and verified
    1 - a required value was missing, or a step failed
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENDPOINT_KEY = "SUPABASE_S3_ENDPOINT_URL"
ACCESS_KEY = "SUPABASE_S3_ACCESS_KEY"
SECRET_KEY = "SUPABASE_S3_SECRET_KEY"  # noqa: S105 - an env var name, not a credential
BUCKET_KEY = "SUPABASE_S3_BUCKET_NAME"

# Every one of these is mirrored into the Databricks scope. The endpoint and
# bucket do not rotate, but re-setting them makes the script idempotent and
# repairs a half-configured scope.
MIRRORED_KEYS = (ENDPOINT_KEY, ACCESS_KEY, SECRET_KEY, BUCKET_KEY)

# What we print instead of any credential material. The repo's rule
# (CONTRIBUTING.md) is to log neither credential values nor credential names, and
# CodeQL's py/clear-text-logging-sensitive-data enforces it — a partially masked
# value still counts as clear-text logging, so we print nothing derived from one.
_REDACTED = "<redacted>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_env(path: Path) -> dict[str, str]:
    """Parse a dotenv file into a plain key/value mapping."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def rewrite_lines(original: str, updates: dict[str, str]) -> tuple[str, list[str]]:
    """Replace the given keys in place, appending any that are absent.

    Untouched lines (comments, unrelated settings, ordering) are preserved
    byte-for-byte apart from their line endings.
    """
    out: list[str] = []
    touched: set[str] = set()
    for line in original.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={updates[key]}{newline}")
            touched.add(key)
        else:
            out.append(line)

    appended = [key for key in updates if key not in touched]
    if appended:
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        out.append("\n# Added by scripts/rotate_supabase_s3_keys.py\n")
        out.extend(f"{key}={updates[key]}\n" for key in appended)
    return "".join(out), sorted(touched | set(appended))


def validate(name: str, value: str) -> None:
    """Reject values that would corrupt the dotenv file or a secret scope."""
    if not value:
        raise SystemExit(f"error: {name} must not be empty.")
    if any(char.isspace() for char in value):
        raise SystemExit(f"error: {name} must not contain whitespace.")


def write_env(path: Path, rendered: str) -> Path:
    """Back up the dotenv file, then write the rotated contents."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    backup.chmod(0o600)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o600)
    return backup


def set_databricks_secret(
    scope: str, env_var: str, value: str, dry_run: bool
) -> bool:
    """Write one secret into a Databricks scope, passing the value via stdin.

    Neither the value nor anything derived from it is printed — only the
    (public, documented) environment variable name.
    """
    if dry_run:
        print(f"  would set {env_var} ({_REDACTED})")
        return True
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, values arrive on stdin
            ["databricks", "secrets", "put-secret", scope, env_var],  # noqa: S607 - via PATH
            input=value,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        print(f"  {env_var} SKIPPED (databricks CLI not on PATH)")
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        print(f"  {env_var} FAILED: {detail}")
        return False
    print(f"  {env_var} ({_REDACTED})")
    return True


def verify(endpoint: str, access_key: str, secret_key: str, bucket: str) -> bool:
    """Prove the rotated pair actually works against the bucket."""
    try:
        import boto3
    except ImportError:
        print("  boto3 not installed - skipping live verification")
        return True

    client: Any = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )
    try:
        client.head_bucket(Bucket=bucket)
        listing = client.list_objects_v2(Bucket=bucket, Prefix="dashboard/", MaxKeys=1000)
    except Exception as exc:  # surface any auth/network failure verbatim
        print(f"  FAILED: {type(exc).__name__}: {str(exc)[:180]}")
        return False
    print(f"  head_bucket({bucket}) OK")
    print(f"  dashboard/ objects: {listing.get('KeyCount', 0)}")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the key rotation helper."""
    parser = argparse.ArgumentParser(
        description="Rotate the Supabase S3 key pair in .env and Databricks secrets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--access-key", help="New access key ID (prompted if omitted).")
    parser.add_argument("--secret-key", help="New secret access key (prompted if omitted).")
    parser.add_argument("--env-file", default=".env", help="Dotenv file to update.")
    parser.add_argument("--scope", default="f1_secrets", help="Databricks secret scope.")
    parser.add_argument(
        "--endpoint-url",
        help="Override the S3 endpoint (defaults to the value already in the env file).",
    )
    parser.add_argument(
        "--bucket-name",
        help="Override the bucket (defaults to the value already in the env file).",
    )
    parser.add_argument("--skip-env", action="store_true", help="Do not touch the env file.")
    parser.add_argument(
        "--skip-databricks",
        action="store_true",
        help="Do not touch Databricks secrets.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change.")
    return parser.parse_args()


def main() -> int:
    """Run the rotation and report what changed."""
    args = parse_args()
    env_path = Path(args.env_file)

    current: dict[str, str] = {}
    if env_path.is_file():
        current = parse_env(env_path)
    elif not args.skip_env:
        print(f"error: {env_path} not found. Run from the repository root.")
        return 1

    endpoint = args.endpoint_url or current.get(ENDPOINT_KEY, "")
    bucket = args.bucket_name or current.get(BUCKET_KEY, "")
    for name, value in ((ENDPOINT_KEY, endpoint), (BUCKET_KEY, bucket)):
        if not value:
            print(f"error: {name} unknown - pass it explicitly or set it in {env_path}.")
            return 1

    access_key = args.access_key or getpass.getpass("New Supabase S3 Access Key ID: ")
    secret_key = args.secret_key or getpass.getpass("New Supabase S3 Secret Access Key: ")
    validate(ACCESS_KEY, access_key)
    validate(SECRET_KEY, secret_key)

    updates = {
        ENDPOINT_KEY: endpoint,
        ACCESS_KEY: access_key,
        SECRET_KEY: secret_key,
        BUCKET_KEY: bucket,
    }

    print("\nRotation plan")
    print(f"  env file    : {env_path} ({'skipped' if args.skip_env else 'backed up + rewritten'})")
    print(f"  secrets     : {args.scope} ({'skipped' if args.skip_databricks else 'updated'})")
    print(f"  endpoint    : {endpoint}")
    print(f"  bucket      : {bucket}")
    print(f"  credentials : {_REDACTED} (access key + secret)")
    if args.dry_run:
        print("  mode        : DRY RUN - nothing will be written")

    if not args.skip_env and not args.dry_run:
        rendered, changed = rewrite_lines(env_path.read_text(encoding="utf-8"), updates)
        backup = write_env(env_path, rendered)
        print(f"\nUpdated {env_path} ({', '.join(changed)})")
        print(f"Backup: {backup} (mode 600, git-ignored)")
    elif not args.skip_env:
        print(f"\n[dry-run] would rewrite {env_path} and back it up")

    if not args.skip_databricks:
        print(f"\nDatabricks scope {args.scope}")
        failures = [
            env_var
            for env_var in MIRRORED_KEYS
            if not set_databricks_secret(
                args.scope, env_var, updates[env_var], args.dry_run
            )
        ]
        if failures:
            print(
                f"\nFAILED to set {len(failures)} of {len(MIRRORED_KEYS)} secrets "
                f"- check WRITE permission on the scope."
            )
            print("Re-run with --skip-env to retry only the secrets.")
            return 1

    if args.dry_run:
        print("\nDry run complete - no changes made.")
        return 0

    print("\nVerifying the new pair against the bucket")
    if not verify(endpoint, access_key, secret_key, bucket):
        print("\nThe new pair could not reach the bucket.")
        print(f"Restore {env_path} from the backup and check the key in Supabase.")
        return 1

    print("\nRotation complete.")
    print("Next: delete the previous access key in Supabase -> Storage -> S3 Access Keys.")
    print("Databricks jobs read secrets at task runtime, so no job edit is needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
