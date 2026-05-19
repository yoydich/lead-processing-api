import os
os.environ["DATABASE_URL"] = "sqlite:///./test_leads.db"

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    """TestClient as context manager ensures lifespan (DB init) runs."""
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_post_lead_accepted(client):
    resp = client.post("/api/leads", json={
        "name": "Ivan Petrov",
        "email": "ivan@test.com",
        "phone": "0671234567",
        "message": "We want SMM services for our startup",
        "source": "test",
    })
    assert resp.status_code == 202
    data = resp.json()
    assert "id" in data
    assert data["status"] == "accepted"


def test_post_lead_invalid_empty_message(client):
    resp = client.post("/api/leads", json={"message": "   "})
    assert resp.status_code == 422


def test_post_lead_no_body(client):
    resp = client.post("/api/leads", json={})
    assert resp.status_code == 422


def test_debug_leads_returns_list(client):
    resp = client.get("/debug/leads?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_deduplication(client):
    payload = {
        "email": "dedup_smoke@test.com",
        "phone": "0992222222",
        "message": "Unique dedup smoke test message payload",
        "source": "test",
    }
    resp1 = client.post("/api/leads", json=payload)
    resp2 = client.post("/api/leads", json=payload)
    assert resp1.status_code == 202
    assert resp2.status_code == 202
    assert resp1.json()["id"] == resp2.json()["id"]
    assert resp2.json()["status"] == "duplicate"
