import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class LeadIn(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    message: str
    source: str = "landing"
    utm: dict[str, str] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if isinstance(v, str):
            cleaned = v.strip().lower()
            return cleaned if cleaned else None
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v):
        if isinstance(v, str):
            digits = re.sub(r"\D+", "", v)
            if len(digits) == 10 and digits.startswith("0"):
                return "38" + digits
            if len(digits) >= 10:
                return digits
            return None
        return v

    @field_validator("name", "company", mode="before")
    @classmethod
    def capitalize_field(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return " ".join(w.capitalize() for w in v.split()) if v else None
        return v

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def validate_contactability(self):
        if not (self.email or self.phone or self.message):
            raise ValueError("Lead must contain at least email, phone, or message")
        return self


class LeadAIResult(BaseModel):
    summary: str
    lead_class: Literal["hot", "warm", "cold", "junk", "manual_review"]
    confidence: int = Field(ge=0, le=100)
    missing_fields: list[str] = []
    reasoning_tags: list[str] = []


class LeadOut(BaseModel):
    id: int
    status: str
    message: str = "Заявку прийнято"


class LeadDebug(BaseModel):
    id: int
    created_at: str
    source: str | None = None
    processing_status: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    message: str | None = None
    ai_summary: str | None = None
    lead_class: str | None = None
    lead_confidence: int | None = None
    telegram_sent: bool | None = None
