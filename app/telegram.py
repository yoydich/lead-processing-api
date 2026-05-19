import html
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import TelegramSubscriber

logger = logging.getLogger(__name__)

TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

CLASS_EMOJI = {
    "hot": "\U0001f525",
    "warm": "\U0001f7e1",
    "cold": "\U0001f535",
    "junk": "\U0001f5d1",
    "manual_review": "\u26a0\ufe0f",
}


def _telegram_token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _send_message(chat_id: str, text: str) -> tuple[bool, str | None]:
    token = _telegram_token()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set"

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                TELEGRAM_SEND_URL.format(token=token),
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            resp.raise_for_status()
            return True, None
    except Exception as exc:
        error = str(exc)
        logger.warning("Telegram send failed for chat_id=%s: %s", chat_id, error)
        return False, error


def _lead_message(lead_data: dict[str, Any]) -> str:
    cls = lead_data.get("lead_class") or ""
    emoji = CLASS_EMOJI.get(cls, "\u26aa")
    confidence = lead_data.get("lead_confidence") or 0
    tags = ", ".join(lead_data.get("reasoning_tags") or []) or "-"

    def esc(value: Any) -> str:
        if value is None or value == "":
            return "-"
        return html.escape(str(value))

    return (
        f"\U0001f514 <b>Нова заявка</b>\n\n"
        f"\U0001f464 <b>Ім'я:</b> {esc(lead_data.get('name'))}\n"
        f"\U0001f4e7 <b>Email:</b> {esc(lead_data.get('email'))}\n"
        f"\U0001f4f1 <b>Телефон:</b> {esc(lead_data.get('phone'))}\n"
        f"\U0001f3e2 <b>Компанія:</b> {esc(lead_data.get('company'))}\n"
        f"\U0001f4ac <b>Повідомлення:</b> {esc(str(lead_data.get('message') or '')[:400])}\n"
        f"\U0001f4cd <b>Джерело:</b> {esc(lead_data.get('source'))}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>Клас:</b> {esc(cls.upper())} ({confidence}%)\n"
        f"\U0001f916 <b>Summary:</b> {esc(lead_data.get('ai_summary'))}\n"
        f"\U0001f3f7 <b>Теги:</b> {esc(tags)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"\U0001f517 Lead ID: <code>{esc(lead_data.get('id'))}</code>"
    )


def list_active_subscribers(db: Session) -> list[TelegramSubscriber]:
    return (
        db.query(TelegramSubscriber)
        .filter(TelegramSubscriber.is_active.is_(True))
        .order_by(TelegramSubscriber.created_at.asc())
        .all()
    )


def upsert_telegram_subscriber(db: Session, message: dict[str, Any]) -> TelegramSubscriber:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        raise ValueError("Telegram update does not contain chat.id")

    now = datetime.now(UTC).replace(tzinfo=None)
    chat_id_str = str(chat_id)
    subscriber = (
        db.query(TelegramSubscriber)
        .filter(TelegramSubscriber.chat_id == chat_id_str)
        .first()
    )

    if subscriber is None:
        subscriber = TelegramSubscriber(chat_id=chat_id_str, created_at=now)
        db.add(subscriber)

    subscriber.username = sender.get("username") or chat.get("username")
    subscriber.first_name = sender.get("first_name") or chat.get("first_name")
    subscriber.last_name = sender.get("last_name") or chat.get("last_name")
    subscriber.chat_type = chat.get("type")
    subscriber.is_active = True
    subscriber.updated_at = now
    db.commit()
    db.refresh(subscriber)
    return subscriber


def deactivate_telegram_subscriber(db: Session, message: dict[str, Any]) -> bool:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return False

    subscriber = (
        db.query(TelegramSubscriber)
        .filter(TelegramSubscriber.chat_id == str(chat_id))
        .first()
    )
    if subscriber is None:
        return False

    subscriber.is_active = False
    subscriber.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    return True


def handle_telegram_update(update: dict[str, Any], db: Session) -> dict[str, Any]:
    message = update.get("message") or update.get("channel_post") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not message or chat_id is None:
        return {"ok": True, "action": "ignored"}

    command = text.split(maxsplit=1)[0].lower()
    if command in {"/start", "/subscribe"}:
        subscriber = upsert_telegram_subscriber(db, message)
        _send_message(
            subscriber.chat_id,
            (
                "Підписку активовано. "
                "Тепер цей чат отримуватиме нові ліди з Lead Processing API.\n\n"
                "Щоб відписатися, надішліть /stop."
            ),
        )
        return {"ok": True, "action": "subscribed", "chat_id": subscriber.chat_id}

    if command in {"/stop", "/unsubscribe"}:
        deactivated = deactivate_telegram_subscriber(db, message)
        _send_message(str(chat_id), "Підписку вимкнено.")
        return {"ok": True, "action": "unsubscribed", "changed": deactivated}

    if command == "/status":
        subscriber_count = len(list_active_subscribers(db))
        _send_message(str(chat_id), f"Активних Telegram-підписників: {subscriber_count}")
        return {"ok": True, "action": "status"}

    _send_message(
        str(chat_id),
        "Команди: /start підписатися, /stop відписатися, /status статус.",
    )
    return {"ok": True, "action": "help"}


def send_telegram_notification(lead_data: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Send a lead card to every active Telegram subscriber.

    Subscribers are created by the Telegram webhook when a user sends /start to the bot.
    The app no longer depends on a single TELEGRAM_CHAT_ID environment variable.
    """
    token = _telegram_token()
    if not token:
        msg = "TELEGRAM_BOT_TOKEN not set"
        logger.warning(msg)
        return False, msg

    text = _lead_message(lead_data)
    db = SessionLocal()
    try:
        subscribers = list_active_subscribers(db)
    finally:
        db.close()

    if not subscribers:
        msg = "No active Telegram subscribers. Send /start to the bot first."
        logger.warning(msg)
        return False, msg

    errors: list[str] = []
    sent_count = 0
    for subscriber in subscribers:
        sent, error = _send_message(subscriber.chat_id, text)
        if sent:
            sent_count += 1
        elif error:
            errors.append(f"{subscriber.chat_id}: {error}")

    if sent_count > 0:
        if errors:
            return True, "; ".join(errors)
        return True, None

    return False, "; ".join(errors) or "Telegram send failed for all subscribers"
