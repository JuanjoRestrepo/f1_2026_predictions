"""Zero-cost cloud cache synchronisation using S3-compatible object storage.

Rationale:
    The FastF1 cache directory (~200MB compressed) contains pre-fetched
    telemetry, timing, and session data. Without persistence, ephemeral
    workers (Trigger.dev / AWS Lambda) re-download everything on each run,
    adding 2-5 minutes of cold-start latency and burning API rate limits.

    Strategy:
        - Pre-run: Download the zipped cache from cloud storage into a local
          ephemeral directory, warm-starting FastF1.
        - Post-run: Zip the updated cache and upload it back, persisting new
          session data for the next run.

    Provider choice — Supabase Storage:
        Supabase exposes an S3-compatible API on their free tier with 1 GB
        of object storage, making it the lowest-friction zero-cost solution.
        boto3 is used rather than the Supabase Python SDK because it
        decouples the implementation from any single vendor — the endpoint_url
        can be swapped for MinIO, Cloudflare R2, or AWS S3 with no code change.

Environment variables (set in .env):
    SUPABASE_S3_ENDPOINT_URL  : Full URL, e.g. https://<project>.supabase.co/storage/v1/s3
    SUPABASE_S3_ACCESS_KEY    : Supabase storage access key
    SUPABASE_S3_SECRET_KEY    : Supabase storage secret key
    SUPABASE_S3_BUCKET_NAME   : Bucket name in Supabase Storage
    SUPABASE_S3_CACHE_KEY     : Object key for the zip archive
                                (default: fastf1_cache.zip)
"""

import io
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Object key used in the S3 bucket to store the cache archive.
# Named constant to avoid magic strings scattered across call sites.
_DEFAULT_CACHE_OBJECT_KEY = "fastf1_cache.zip"


def _get_s3_client() -> "botocore.client.S3":  # type: ignore[name-defined]  # noqa: F821
    """Lazily build an S3 client from environment variables.

    Deferred import of boto3 so this module can be imported even when
    boto3 is not installed (cloud cache is opt-in, not mandatory).

    Returns:
        A configured boto3 S3 client with S3-compatible endpoint.

    Raises:
        ImportError: If boto3 is not installed.
        ValueError: If required environment variables are missing.
    """
    try:
        import boto3
    except ImportError as exc:
        msg = "boto3 is required for cloud cache. Run: uv add 'boto3>=1.35.0'"
        raise ImportError(msg) from exc

    import os

    endpoint_url = os.environ.get("SUPABASE_S3_ENDPOINT_URL")
    access_key = os.environ.get("SUPABASE_S3_ACCESS_KEY")
    secret_key = os.environ.get("SUPABASE_S3_SECRET_KEY")

    missing = [
        name
        for name, val in [
            ("SUPABASE_S3_ENDPOINT_URL", endpoint_url),
            ("SUPABASE_S3_ACCESS_KEY", access_key),
            ("SUPABASE_S3_SECRET_KEY", secret_key),
        ]
        if not val
    ]
    if missing:
        msg = (
            f"Cloud cache is enabled but the following environment variables "
            f"are not set: {', '.join(missing)}. "
            f"Set them in .env or CI/CD secrets."
        )
        raise ValueError(msg)

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # region_name is required by boto3 even for non-AWS endpoints.
        # "us-east-1" is a universally accepted placeholder for S3-compatible APIs.
        region_name="us-east-1",
    )


def _zip_directory(source_dir: Path) -> bytes:
    """Zip a directory tree into an in-memory byte buffer.

    Uses ZIP_DEFLATED compression (standard zlib) to achieve ~60-70%
    size reduction on the FastF1 cache. LZMA would be smaller but adds
    significant CPU overhead on CI workers.

    Args:
        source_dir: Path to the directory to archive.

    Returns:
        Bytes of the zip archive.

    Raises:
        FileNotFoundError: If source_dir does not exist.
    """
    if not source_dir.exists():
        msg = f"Cache directory not found: {source_dir}"
        raise FileNotFoundError(msg)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)
    return buf.getvalue()


def _unzip_to_directory(archive_bytes: bytes, dest_dir: Path) -> None:
    """Extract a zip archive from bytes into a destination directory.

    Creates dest_dir and all parents if they do not exist.

    Args:
        archive_bytes: Raw zip archive bytes.
        dest_dir: Directory to extract files into.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        zf.extractall(dest_dir)


def download_cache(
    local_cache_dir: Path,
    bucket_name: str | None = None,
    object_key: str = _DEFAULT_CACHE_OBJECT_KEY,
) -> bool:
    """Download the FastF1 cache archive from cloud storage and extract it.

    This is the pre-pipeline hook. Call it before ``fastf1.Cache.enable_cache()``
    so that the local directory is populated with previously-fetched session data,
    eliminating redundant network round-trips to the FastF1 CDN.

    Args:
        local_cache_dir: Local directory where the cache will be extracted.
            Typically ``settings.fastf1_cache_dir`` (e.g. ``Path("fastf1_cache")``).
        bucket_name: S3 bucket name. Falls back to ``SUPABASE_S3_BUCKET_NAME``
            environment variable if not provided.
        object_key: Object key in the bucket (default: ``fastf1_cache.zip``).

    Returns:
        True if the cache was downloaded and extracted successfully.
        False if the object does not exist in the bucket (first run) or
        any non-fatal error occurs — the pipeline continues without cache.

    Raises:
        ValueError: If bucket_name cannot be resolved from argument or env var.
    """
    import os

    resolved_bucket = bucket_name or os.environ.get("SUPABASE_S3_BUCKET_NAME")
    if not resolved_bucket:
        msg = (
            "bucket_name must be provided or SUPABASE_S3_BUCKET_NAME "
            "must be set in environment."
        )
        raise ValueError(msg)

    logger.info(
        "Downloading FastF1 cloud cache from s3://%s/%s → %s",
        resolved_bucket,
        object_key,
        local_cache_dir,
    )

    try:
        s3 = _get_s3_client()
        response = s3.get_object(Bucket=resolved_bucket, Key=object_key)
        archive_bytes = response["Body"].read()
        _unzip_to_directory(archive_bytes, local_cache_dir)
    except Exception as exc:
        # Catching broad Exception because botocore.exceptions are conditionally
        # available and we must not hard-fail the pipeline on a cache miss.
        # NoSuchKey = first run (acceptable); other errors = warn and continue.
        logger.warning(
            "Cloud cache download failed (pipeline continues without cache): %s",
            exc,
        )
        return False
    else:
        logger.info(
            "Cloud cache downloaded and extracted: %d bytes → %s",
            len(archive_bytes),
            local_cache_dir,
        )
        return True


def upload_cache(
    local_cache_dir: Path,
    bucket_name: str | None = None,
    object_key: str = _DEFAULT_CACHE_OBJECT_KEY,
) -> bool:
    """Zip the local FastF1 cache and upload it to cloud storage.

    This is the post-pipeline hook. Call it after the pipeline completes
    to persist any newly-downloaded session data for the next run.

    Args:
        local_cache_dir: Path to the local FastF1 cache directory.
        bucket_name: S3 bucket name. Falls back to ``SUPABASE_S3_BUCKET_NAME``
            environment variable if not provided.
        object_key: Object key in the bucket (default: ``fastf1_cache.zip``).

    Returns:
        True if the upload succeeded.
        False on any error — the pipeline has already completed so this is
        non-fatal; it just means the cache won't be warm on the next run.

    Raises:
        ValueError: If bucket_name cannot be resolved.
    """
    import os

    resolved_bucket = bucket_name or os.environ.get("SUPABASE_S3_BUCKET_NAME")
    if not resolved_bucket:
        msg = (
            "bucket_name must be provided or SUPABASE_S3_BUCKET_NAME "
            "must be set in environment."
        )
        raise ValueError(msg)

    if not local_cache_dir.exists():
        logger.warning(
            "Cache directory does not exist, skipping upload: %s", local_cache_dir
        )
        return False

    logger.info(
        "Uploading FastF1 cache to s3://%s/%s from %s",
        resolved_bucket,
        object_key,
        local_cache_dir,
    )

    try:
        archive_bytes = _zip_directory(local_cache_dir)
        s3 = _get_s3_client()
        s3.put_object(
            Bucket=resolved_bucket,
            Key=object_key,
            Body=archive_bytes,
            ContentType="application/zip",
        )
    except Exception as exc:
        logger.warning("Cloud cache upload failed (non-fatal): %s", exc)
        return False
    else:
        logger.info(
            "Cloud cache uploaded: %d bytes → s3://%s/%s",
            len(archive_bytes),
            resolved_bucket,
            object_key,
        )
        return True
