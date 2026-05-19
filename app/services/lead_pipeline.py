import json
import logging

from ..db import SessionLocal
from ..models import Lead
from ..schemas import LeadIn
from ..llm import analyze_lead
from ..telegram import send_telegram_notification

logger = logging.getLogger(__name__)


def process_lead_pipeline(lead_id: int, lead: LeadIn) -> None:
    """
    Full async pipeline — runs as a FastAPI BackgroundTask after 202 is returned.
    Creates its own DB session (the request session is already closed).

    Steps:
        1. Save normalized data
        2. Run AI analysis (OpenAI Structured Outputs)
        3. Update DB with AI results
        4. Send Telegram notification
    """
    db = SessionLocal()
    ai_result = None
    try:
        db_lead = db.get(Lead, lead_id)
        if not db_lead:
            logger.error(f"Lead {lead_id} not found — skipping pipeline")
            return

        # ── Step 1: persist normalized fields ─────────────────────────────
        db_lead.processing_status = "processing"
        db_lead.normalized_payload_json = json.dumps(
            lead.model_dump(), ensure_ascii=False
        )
        db_lead.name = lead.name
        db_lead.email = lead.email
        db_lead.phone = lead.phone
        db_lead.company = lead.company
        db_lead.message = lead.message
        db.commit()

        # ── Step 2: AI analysis ────────────────────────────────────────────
        try:
            ai_result = analyze_lead(lead)
            db_lead.ai_summary = ai_result.summary
            db_lead.lead_class = ai_result.lead_class
            db_lead.lead_confidence = ai_result.confidence
            db_lead.ai_model = "gpt-4o-mini"
            db_lead.processing_status = "done"
        except Exception as e:
            logger.error(f"AI step failed for lead {lead_id}: {e}")
            db_lead.processing_status = "error"
            db_lead.lead_class = "manual_review"
            db_lead.lead_confidence = 0
        db.commit()

        # ── Step 3: Telegram notification ─────────────────────────────────
        tg_payload = {
            "id": lead_id,
            "name": db_lead.name,
            "email": db_lead.email,
            "phone": db_lead.phone,
            "company": db_lead.company,
            "message": db_lead.message,
            "source": db_lead.source,
            "lead_class": db_lead.lead_class,
            "lead_confidence": db_lead.lead_confidence,
            "ai_summary": db_lead.ai_summary,
            "reasoning_tags": ai_result.reasoning_tags if ai_result else [],
        }
        sent, error = send_telegram_notification(tg_payload)
        db_lead.telegram_sent = sent
        db_lead.telegram_error = error
        db.commit()

        logger.info(
            f"Lead {lead_id} processed | class={db_lead.lead_class} "
            f"confidence={db_lead.lead_confidence} telegram={sent}"
        )

    except Exception as e:
        logger.exception(f"Pipeline crashed for lead {lead_id}: {e}")
        try:
            db_lead = db.get(Lead, lead_id)
            if db_lead:
                db_lead.processing_status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
