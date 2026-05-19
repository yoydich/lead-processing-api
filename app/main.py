import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, UTC
from typing import Annotated

from fastapi import FastAPI, Depends, BackgroundTasks, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from .db import engine, get_db, Base
from .models import Lead
from .schemas import LeadIn, LeadOut, LeadDebug
from .services.lead_pipeline import process_lead_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready")
    yield


app = FastAPI(
    title="Lead Processing MVP",
    description=(
        "Automated pipeline for landing-page leads: "
        "validation → normalization → AI summary/classification → Google Sheets → Telegram"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/leads", response_model=LeadOut, status_code=202)
async def create_lead(
    lead: LeadIn,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Accept a lead from a landing-page form.

    Returns **202 Accepted** immediately.
    AI analysis + Telegram notification run in background.

    Deduplication: same email+phone+message[:100] within 24 hours → returns existing id.
    """
    # ── Deduplication ─────────────────────────────────────────────────────
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    filters = [Lead.created_at > cutoff]
    if lead.email:
        filters.append(Lead.email == lead.email)
    if lead.phone:
        filters.append(Lead.phone == lead.phone)
    if lead.message:
        msg_prefix = lead.message[:100]
        filters.append(Lead.message.startswith(msg_prefix))

    if len(filters) > 1:  # at least one contact field matched
        duplicate = db.query(Lead).filter(and_(*filters)).first()
        if duplicate:
            logger.info(f"Duplicate lead detected → id={duplicate.id}")
            return LeadOut(
                id=duplicate.id,
                status="duplicate",
                message="Заявку вже отримано раніше",
            )

    # ── Save raw lead to DB immediately ───────────────────────────────────
    db_lead = Lead(
        source=lead.source,
        processing_status="pending",
        raw_payload_json=json.dumps(lead.model_dump(), ensure_ascii=False),
        message=lead.message,
    )
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    lead_id = db_lead.id

    # ── Schedule background pipeline ──────────────────────────────────────
    background_tasks.add_task(process_lead_pipeline, lead_id, lead)

    logger.info(f"Lead {lead_id} accepted — pipeline scheduled")
    return LeadOut(id=lead_id, status="accepted")


@app.get("/debug/leads", response_model=list[LeadDebug])
def get_leads(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Return recent leads with processing results.
    For inspection and demo purposes.
    """
    leads = db.query(Lead).order_by(Lead.created_at.desc()).limit(limit).all()
    return [
        LeadDebug(
            id=l.id,
            created_at=l.created_at.isoformat() if l.created_at else "",
            source=l.source,
            processing_status=l.processing_status,
            name=l.name,
            email=l.email,
            phone=l.phone,
            company=l.company,
            message=(l.message or "")[:200],
            ai_summary=l.ai_summary,
            lead_class=l.lead_class,
            lead_confidence=l.lead_confidence,
            telegram_sent=l.telegram_sent,
        )
        for l in leads
    ]


@app.get("/health")
def health():
    return {"status": "ok", "service": "lead-processing-mvp", "version": "1.0.0"}
