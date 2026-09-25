import httpx
import pytest

from app.core.config import Settings
from app.modules.google_workspace import service


@pytest.mark.parametrize(
    ("exception_type", "expected_status", "detail_fragment"),
    [
        (httpx.ReadTimeout, 504, "did not respond before the server timeout"),
        (httpx.ConnectError, 502, "could not contact Google Workspace"),
    ],
)
def test_google_request_transport_failure_has_actionable_reason(
    monkeypatch, exception_type, expected_status, detail_fragment
):
    def fail_request(*args, **kwargs):
        raise exception_type("upstream unavailable")

    monkeypatch.setattr(httpx, "request", fail_request)

    with pytest.raises(service.GoogleWorkspaceError) as raised:
        service._request("GET", "https://www.googleapis.com/example")

    assert raised.value.status_code == expected_status
    assert detail_fragment in raised.value.detail


def test_google_workspace_settings_are_available_to_oauth_service():
    configured = Settings(
        database_url="sqlite://",
        jwt_secret_key="test-secret-key-long-enough",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="https://example.test/api/v1/google-workspace/callback",
        google_allowed_workspace_domain="example.test",
        google_token_encryption_key="separate-test-key",
    )

    assert configured.google_oauth_client_id == "client-id"
    assert configured.google_allowed_workspace_domain == "example.test"
    assert configured.google_workspace_timeout_seconds == 15
