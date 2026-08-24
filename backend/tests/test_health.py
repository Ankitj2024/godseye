"""Smoke tests for the backend health and jobs API."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "godseye-backend"


def test_list_jobs_empty(client):
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_job_no_file(client):
    """Creating a job without a file should return 422."""
    response = client.post("/api/jobs")
    assert response.status_code == 422


def test_stub_endpoints_return_501(client):
    """Future endpoints should return 501 Not Implemented."""
    fake_id = "nonexistent123"
    stubs = [
        f"/api/jobs/{fake_id}/scene",
        f"/api/jobs/{fake_id}/detections",
        f"/api/jobs/{fake_id}/scene-graph",
        f"/api/jobs/{fake_id}/confidence",
        f"/api/jobs/{fake_id}/download",
    ]
    for path in stubs:
        response = client.get(path)
        assert response.status_code == 501, f"Expected 501 for {path}"
