from datetime import datetime, UTC
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from .db import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), index=True)
    source = Column(String, default="landing")
    processing_status = Column(String, default="pending")  # pending/processing/done/error

    # Payloads
    raw_payload_json = Column(Text)
    normalized_payload_json = Column(Text)

    # Normalized contact fields
    name = Column(String)
    email = Column(String, index=True)
    phone = Column(String)
    company = Column(String)
    message = Column(Text)

    # AI results
    ai_summary = Column(Text)
    lead_class = Column(String)       # hot / warm / cold / junk / manual_review
    lead_confidence = Column(Integer)
    ai_model = Column(String)

    # Notification
    telegram_sent = Column(Boolean, default=False)
    telegram_error = Column(String)
