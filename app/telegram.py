import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

CLASS_EMOJI = {
    "hot": "🔥",
    "warm": "🟡",
    "cold": "🔵",
    "junk": "🗑",
    "manual_review": "⚠️",
}


def send_telegram_notification(lead_data: dict) -> tuple[bool, str | None]:
    """
    Send lead card to Telegram. Returns (success, error_message).
    Uses plain httpx (sync) — called from background thread.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        msg = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"
        logger.warning(msg)
        return False, msg

    cls = lead_data.get("lead_class", "")
    emoji = CLASS_EMOJI.get(cls, "⚪")
    confidence = lead_data.get("lead_confidence") or 0
    tags = ", ".join(lead_data.get("reasoning_tags") or []) or "—"

    text = (
        f"🔔 <b>Нова заявка!</b>\n\n"
        f"👤 <b>Ім'я:</b> {lead_data.get('name') or '—'}\n"
        f"📧 <b>Email:</b> {lead_data.get('email') or '—'}\n"
        f"📱 <b>Телефон:</b> {lead_data.get('phone') or '—'}\n"
        f"🏢 <b>Компанія:</b> {lead_data.get('company') or '—'}\n"
        f"💬 <b>Повідомлення:</b> {str(lead_data.get('message', ''))[:400]}\n"
        f"📍 <b>Джерело:</b> {lead_data.get('source') or '—'}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>Клас:</b> {cls.upper()} ({confidence}%)\n"
        f"🤖 <b>Summary:</b> {lead_data.get('ai_summary') or '—'}\n"
        f"🏷 <b>Теги:</b> {tags}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🔗 Lead ID: <code>{lead_data.get('id')}</code>"
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                TELEGRAM_URL.format(token=token),
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            resp.raise_for_status()
            return True, None
    except Exception as e:
        error = str(e)
        logger.error(f"Telegram notification failed: {error}")
        return False, error
