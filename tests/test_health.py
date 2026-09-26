"""Health endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Provide a test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test that the health endpoint returns ok status and the active retrieval mode."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["retrieval_mode"] in ("vector", "hybrid")
