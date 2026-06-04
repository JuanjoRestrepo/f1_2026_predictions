"""Unit tests for f1_predictions.utils.cloud_cache.

All AWS/boto3 calls are mocked via unittest.mock.patch so these tests
run without network access, AWS credentials, or boto3 installed in a
minimal test environment. The actual filesystem operations (zip/unzip)
are tested against a real temporary directory.
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_s3_client_mock() -> MagicMock:
    """Build a minimal mock boto3 S3 client."""
    return MagicMock()


def _create_cache_dir(tmp_path: Path) -> Path:
    """Populate a temporary directory with a realistic FastF1 cache structure."""
    cache = tmp_path / "fastf1_cache"
    cache.mkdir()
    (cache / "subdir").mkdir()
    (cache / "session_2026_bahrain.pkl").write_bytes(b"fake-session-data")
    (cache / "subdir" / "lap_times.csv").write_bytes(b"lap,time\n1,90.5\n")
    return cache


# ---------------------------------------------------------------------------
# _zip_directory / _unzip_to_directory tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestZipHelpers:
    """Tests for the internal zip/unzip utility functions."""

    def test_zip_produces_valid_archive(self, tmp_path: Path) -> None:
        """_zip_directory must produce bytes that are a valid zip archive."""
        from f1_predictions.utils.cloud_cache import _zip_directory

        cache = _create_cache_dir(tmp_path)
        archive = _zip_directory(cache)

        assert isinstance(archive, bytes)
        assert len(archive) > 0
        # Validate it is actually a valid zip file
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            names = zf.namelist()
        assert "session_2026_bahrain.pkl" in names
        assert (
            str(Path("subdir") / "lap_times.csv") in names
            or "subdir/lap_times.csv" in names
        )

    def test_zip_raises_on_missing_directory(self, tmp_path: Path) -> None:
        """_zip_directory raises FileNotFoundError for non-existent paths."""
        from f1_predictions.utils.cloud_cache import _zip_directory

        with pytest.raises(FileNotFoundError):
            _zip_directory(tmp_path / "does_not_exist")

    def test_unzip_restores_files(self, tmp_path: Path) -> None:
        """_unzip_to_directory must faithfully restore all archived files."""
        from f1_predictions.utils.cloud_cache import _unzip_to_directory, _zip_directory

        cache = _create_cache_dir(tmp_path)
        archive = _zip_directory(cache)

        restore_dir = tmp_path / "restored"
        _unzip_to_directory(archive, restore_dir)

        assert (restore_dir / "session_2026_bahrain.pkl").exists()
        assert (restore_dir / "subdir" / "lap_times.csv").exists()
        # Validate content is identical
        assert (
            restore_dir / "session_2026_bahrain.pkl"
        ).read_bytes() == b"fake-session-data"

    def test_unzip_creates_dest_dir(self, tmp_path: Path) -> None:
        """_unzip_to_directory creates the destination directory if absent."""
        from f1_predictions.utils.cloud_cache import _unzip_to_directory, _zip_directory

        cache = _create_cache_dir(tmp_path)
        archive = _zip_directory(cache)

        new_dest = tmp_path / "brand_new" / "nested"
        assert not new_dest.exists()
        _unzip_to_directory(archive, new_dest)
        assert new_dest.exists()


# ---------------------------------------------------------------------------
# download_cache tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDownloadCache:
    """Tests for cloud_cache.download_cache()."""

    def test_returns_true_on_success(self, tmp_path: Path) -> None:
        """download_cache returns True when S3 get_object succeeds."""
        # Build a real archive to return from the mock
        _create_cache_dir(tmp_path)
        archive = _zip_directory_helper(tmp_path)

        mock_s3 = _make_s3_client_mock()
        mock_s3.get_object.return_value = {"Body": io.BytesIO(archive)}

        with (
            patch(
                "f1_predictions.utils.cloud_cache._get_s3_client", return_value=mock_s3
            ),
            patch.dict("os.environ", {"SUPABASE_S3_BUCKET_NAME": "test-bucket"}),
        ):
            from f1_predictions.utils.cloud_cache import download_cache

            dest = tmp_path / "extracted"
            result = download_cache(dest, bucket_name="test-bucket")

        assert result is True

    def test_returns_false_on_s3_error(self, tmp_path: Path) -> None:
        """download_cache returns False (non-fatal) when S3 raises an error."""
        mock_s3 = _make_s3_client_mock()
        mock_s3.get_object.side_effect = Exception("NoSuchKey")

        with (
            patch(
                "f1_predictions.utils.cloud_cache._get_s3_client", return_value=mock_s3
            ),
            patch.dict("os.environ", {"SUPABASE_S3_BUCKET_NAME": "test-bucket"}),
        ):
            from f1_predictions.utils.cloud_cache import download_cache

            result = download_cache(tmp_path / "cache", bucket_name="test-bucket")

        assert result is False

    def test_raises_value_error_when_no_bucket(self, tmp_path: Path) -> None:
        """download_cache raises ValueError if bucket_name cannot be resolved."""
        # Ensure env var is not set
        with patch.dict("os.environ", {}, clear=True):
            # Remove SUPABASE_S3_BUCKET_NAME if present
            import os

            os.environ.pop("SUPABASE_S3_BUCKET_NAME", None)

            from f1_predictions.utils.cloud_cache import download_cache

            with pytest.raises(ValueError, match="SUPABASE_S3_BUCKET_NAME"):
                download_cache(tmp_path / "cache")  # No bucket arg, no env var


# ---------------------------------------------------------------------------
# upload_cache tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadCache:
    """Tests for cloud_cache.upload_cache()."""

    def test_returns_true_on_success(self, tmp_path: Path) -> None:
        """upload_cache returns True when S3 put_object succeeds."""
        cache = _create_cache_dir(tmp_path)

        mock_s3 = _make_s3_client_mock()
        mock_s3.put_object.return_value = {}

        with (
            patch(
                "f1_predictions.utils.cloud_cache._get_s3_client", return_value=mock_s3
            ),
            patch.dict("os.environ", {"SUPABASE_S3_BUCKET_NAME": "test-bucket"}),
        ):
            from f1_predictions.utils.cloud_cache import upload_cache

            result = upload_cache(cache, bucket_name="test-bucket")

        assert result is True

    def test_put_object_called_with_zip_bytes(self, tmp_path: Path) -> None:
        """upload_cache must call put_object with valid zip bytes in Body."""
        cache = _create_cache_dir(tmp_path)

        mock_s3 = _make_s3_client_mock()
        mock_s3.put_object.return_value = {}

        with (
            patch(
                "f1_predictions.utils.cloud_cache._get_s3_client", return_value=mock_s3
            ),
            patch.dict("os.environ", {"SUPABASE_S3_BUCKET_NAME": "test-bucket"}),
        ):
            from f1_predictions.utils.cloud_cache import upload_cache

            upload_cache(cache, bucket_name="test-bucket")

        call_kwargs = mock_s3.put_object.call_args.kwargs
        body = call_kwargs["Body"]
        # Validate the bytes are a valid zip file
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            assert len(zf.namelist()) > 0

    def test_returns_false_on_s3_error(self, tmp_path: Path) -> None:
        """upload_cache returns False (non-fatal) when put_object raises."""
        cache = _create_cache_dir(tmp_path)

        mock_s3 = _make_s3_client_mock()
        mock_s3.put_object.side_effect = Exception("AccessDenied")

        with (
            patch(
                "f1_predictions.utils.cloud_cache._get_s3_client", return_value=mock_s3
            ),
            patch.dict("os.environ", {"SUPABASE_S3_BUCKET_NAME": "test-bucket"}),
        ):
            from f1_predictions.utils.cloud_cache import upload_cache

            result = upload_cache(cache, bucket_name="test-bucket")

        assert result is False

    def test_returns_false_when_cache_dir_absent(self, tmp_path: Path) -> None:
        """upload_cache returns False if the cache directory does not exist."""
        from f1_predictions.utils.cloud_cache import upload_cache

        result = upload_cache(tmp_path / "nonexistent_cache", bucket_name="test-bucket")

        assert result is False

    def test_raises_value_error_when_no_bucket(self, tmp_path: Path) -> None:
        """upload_cache raises ValueError when bucket cannot be resolved."""
        cache = _create_cache_dir(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os

            os.environ.pop("SUPABASE_S3_BUCKET_NAME", None)

            from f1_predictions.utils.cloud_cache import upload_cache

            with pytest.raises(ValueError, match="SUPABASE_S3_BUCKET_NAME"):
                upload_cache(cache)


# ---------------------------------------------------------------------------
# Helpers used inside test methods (avoids import circularity)
# ---------------------------------------------------------------------------


def _zip_directory_helper(tmp_path: Path) -> bytes:
    """Create a real zip archive from the tmp cache dir for mock responses."""
    from f1_predictions.utils.cloud_cache import _zip_directory

    cache = tmp_path / "fastf1_cache"
    if not cache.exists():
        _create_cache_dir(tmp_path)
    return _zip_directory(cache)
