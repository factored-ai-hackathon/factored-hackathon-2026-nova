import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "s3cret")
    get_settings.cache_clear()
    yield "s3cret"
    get_settings.cache_clear()


def test_requests_without_the_cloudfront_secret_are_rejected(secret):
    with TestClient(app) as client:
        assert client.get("/health").status_code == 403
        assert client.get("/health", headers={"X-Origin-Verify": "wrong"}).status_code == 403
        assert client.get("/health", headers={"X-Origin-Verify": secret}).status_code == 200


def test_no_check_when_secret_is_unset():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
