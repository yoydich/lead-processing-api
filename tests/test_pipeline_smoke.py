import os
import json
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./test_leads.db"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Lead, TelegramSubscriber
import app.telegram as telegram


@pytest.fixture(scope="module")
def client():
    """TestClient as context manager ensures lifespan (DB init) runs."""
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["database"] == {
        "backend": "sqlite",
        "config_source": "env:DATABASE_URL",
        "persistent": False,
        "railway": False,
    }


def test_post_lead_accepted(client):
    unique_email = f"ivan-{uuid4().hex}@test.com"
    resp = client.post("/api/leads", json={
        "name": "Ivan Petrov",
        "email": unique_email,
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


def test_openapi_has_lead_examples(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    body_schema = resp.json()["paths"]["/api/leads"]["post"]["requestBody"]
    examples = body_schema["content"]["application/json"]["examples"]
    assert "hot_lead" in examples
    assert examples["hot_lead"]["value"]["source"] == "swagger_demo"


def test_raw_payload_is_preserved_before_normalization(client):
    raw_name = "  iVAN   PETROV  "
    raw_email = f" RAW-{uuid4().hex}@Example.COM "
    payload = {
        "name": raw_name,
        "email": raw_email,
        "phone": "+38 (067) 123-45-67",
        "message": "Need ads audit",
        "source": "raw-test",
    }

    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 202
    lead_id = resp.json()["id"]

    with SessionLocal() as db:
        db_lead = db.get(Lead, lead_id)
        assert db_lead is not None
        raw_payload = json.loads(db_lead.raw_payload_json)
        normalized_payload = json.loads(db_lead.normalized_payload_json)

    assert raw_payload["name"] == raw_name
    assert raw_payload["email"] == raw_email
    assert normalized_payload["name"] == "Ivan Petrov"
    assert normalized_payload["email"] == raw_email.strip().lower()


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


def test_telegram_webhook_subscribes_chat(client):
    chat_id = f"tg-{uuid4().hex}"
    resp = client.post("/api/telegram/webhook", json={
        "update_id": 1001,
        "message": {
            "message_id": 1,
            "text": "/start",
            "chat": {"id": chat_id, "type": "private"},
            "from": {
                "id": chat_id,
                "is_bot": False,
                "first_name": "Test",
                "username": "leadtester",
            },
        },
    })

    assert resp.status_code == 200
    assert resp.json()["action"] == "subscribed"

    with SessionLocal() as db:
        subscriber = (
            db.query(TelegramSubscriber)
            .filter(TelegramSubscriber.chat_id == chat_id)
            .first()
        )
        assert subscriber is not None
        assert subscriber.is_active is True
        assert subscriber.username == "leadtester"


def test_telegram_notification_broadcasts_to_subscribers(monkeypatch, client):
    chat_id = f"tg-{uuid4().hex}"
    with SessionLocal() as db:
        db.add(TelegramSubscriber(chat_id=chat_id, is_active=True))
        db.commit()

    sent_messages = []

    def fake_send_message(chat_id, text):
        sent_messages.append((chat_id, text))
        return True, None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(telegram, "_send_message", fake_send_message)

    sent, error = telegram.send_telegram_notification({
        "id": 1,
        "name": "Ivan Petrov",
        "message": "Need ads",
        "lead_class": "hot",
        "lead_confidence": 95,
        "ai_summary": "Hot lead",
        "reasoning_tags": ["budget"],
    })

    assert sent is True
    assert error is None
    assert any(message[0] == chat_id for message in sent_messages)


def test_telegram_webhook_unsubscribes_chat(client):
    chat_id = f"tg-{uuid4().hex}"
    with SessionLocal() as db:
        db.add(TelegramSubscriber(chat_id=chat_id, is_active=True))
        db.commit()

    resp = client.post("/api/telegram/webhook", json={
        "update_id": 1002,
        "message": {
            "message_id": 1,
            "text": "/stop",
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False},
        },
    })

    assert resp.status_code == 200
    assert resp.json()["action"] == "unsubscribed"

    with SessionLocal() as db:
        subscriber = (
            db.query(TelegramSubscriber)
            .filter(TelegramSubscriber.chat_id == chat_id)
            .first()
        )
        assert subscriber is not None
        assert subscriber.is_active is False
