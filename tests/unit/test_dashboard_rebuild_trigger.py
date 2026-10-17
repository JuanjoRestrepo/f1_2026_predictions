"""Unit tests for the Vercel rebuild trigger in databricks_entrypoint.py.

Publishing a bundle is not enough to make a new round reachable: the dashboard
pulls ``reports/`` at build time and derives its round list from
``getStaticPaths``, so the site has to be rebuilt. The trigger is deliberately
best-effort — it must never fail the export task — which is what these tests pin.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import databricks_entrypoint as entry

_HOOK = "https://api.vercel.com/v1/integrations/deploy/prj/abc123"


@pytest.fixture(autouse=True)
def _no_secret_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never reach for a real Databricks scope during these tests."""
    monkeypatch.setattr(
        entry, "_load_secrets_from_databricks", lambda *args, **kwargs: None
    )


def test_no_hook_configured_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a hook URL the task simply notes it and moves on."""
    monkeypatch.delenv(entry._DEPLOY_HOOK_ENV_VAR, raising=False)

    with patch("requests.post") as post:
        entry._trigger_dashboard_rebuild()

    post.assert_not_called()


def test_hook_is_posted_with_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook receives a POST, and a hung endpoint cannot stall the job."""
    monkeypatch.setenv(entry._DEPLOY_HOOK_ENV_VAR, _HOOK)

    with patch(
        "requests.post", return_value=SimpleNamespace(ok=True, status_code=201)
    ) as post:
        entry._trigger_dashboard_rebuild()

    post.assert_called_once_with(_HOOK, timeout=30)


def test_hook_is_read_from_the_secret_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hook stored only in f1_secrets must still be picked up."""
    monkeypatch.delenv(entry._DEPLOY_HOOK_ENV_VAR, raising=False)

    def fake_loader(env_vars: tuple[str, ...], label: str) -> None:
        assert env_vars == (entry._DEPLOY_HOOK_ENV_VAR,)
        monkeypatch.setenv(entry._DEPLOY_HOOK_ENV_VAR, _HOOK)

    with (
        patch.object(entry, "_load_secrets_from_databricks", side_effect=fake_loader),
        patch(
            "requests.post", return_value=SimpleNamespace(ok=True, status_code=201)
        ) as post,
    ):
        entry._trigger_dashboard_rebuild()

    post.assert_called_once_with(_HOOK, timeout=30)


def test_request_failure_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead hook must not fail the export task."""
    monkeypatch.setenv(entry._DEPLOY_HOOK_ENV_VAR, _HOOK)

    with patch("requests.post", side_effect=RuntimeError("connection reset")):
        entry._trigger_dashboard_rebuild()


def test_rejected_hook_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-2xx response is logged, not raised."""
    monkeypatch.setenv(entry._DEPLOY_HOOK_ENV_VAR, _HOOK)

    with patch(
        "requests.post", return_value=SimpleNamespace(ok=False, status_code=404)
    ):
        entry._trigger_dashboard_rebuild()


def test_run_export_triggers_a_rebuild_after_publishing() -> None:
    """The rebuild follows a successful publish, once."""
    with (
        patch(
            "f1_predictions.utils.dashboard_publish.publish_dashboard_data",
            return_value={"published": 292},
        ) as publish,
        patch.object(entry, "_trigger_dashboard_rebuild") as trigger,
    ):
        entry.run_export(2026)

    publish.assert_called_once()
    trigger.assert_called_once_with()


def test_run_export_does_not_trigger_when_publishing_fails() -> None:
    """No publish means nothing to serve, so the site is left alone."""
    with (
        patch(
            "f1_predictions.utils.dashboard_publish.publish_dashboard_data",
            side_effect=RuntimeError("bucket unreachable"),
        ),
        patch.object(entry, "_trigger_dashboard_rebuild") as trigger,
    ):
        entry.run_export(2026)

    trigger.assert_not_called()
