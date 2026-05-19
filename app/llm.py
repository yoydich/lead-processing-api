import os
import json
import logging
from openai import OpenAI
from .schemas import LeadIn, LeadAIResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ти асистент маркетингового агентства. Аналізуй заявки з лендінгу та класифікуй ліди.

Критерії класифікації:
- hot:           є контакт + чіткий конкретний запит + бюджет або дедлайн або demo_request
- warm:          є інтерес та базовий запит, але немає бюджету або запит розмитий
- cold:          загальне питання, мінімум деталей, немає конкретного наміру
- junk:          спам, тест, нерелевантний або безглуздий запит
- manual_review: AI не впевнений або суперечливі сигнали

Summary: 1-2 конкретні речення — хто лід, що хоче, чому цікавий або не цікавий.
Не пиши "Лід X запитує про..." — описуй суть фактично.

Відповідай ТІЛЬКИ валідним JSON без markdown та коментарів:
{
  "summary": "...",
  "lead_class": "hot|warm|cold|junk|manual_review",
  "confidence": 0-100,
  "missing_fields": [],
  "reasoning_tags": []
}"""


def analyze_lead(lead: LeadIn) -> LeadAIResult:
    """
    Call OpenRouter (OpenAI-compatible) to analyze and classify a lead.
    Uses Chat Completions with JSON mode — works with any OpenRouter model.
    Falls back to manual_review on any error.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    user_content = (
        f"Ім'я: {lead.name or '—'}\n"
        f"Email: {lead.email or '—'}\n"
        f"Телефон: {lead.phone or '—'}\n"
        f"Компанія: {lead.company or '—'}\n"
        f"Повідомлення: {lead.message}\n"
        f"Джерело: {lead.source}\n"
        f"UTM: {lead.utm or 'відсутній'}"
    )

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        # Strip accidental markdown fences if model adds them
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = LeadAIResult.model_validate_json(content)
        return result

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return LeadAIResult(
            summary="Не вдалося проаналізувати заявку автоматично.",
            lead_class="manual_review",
            confidence=0,
            missing_fields=[],
            reasoning_tags=["llm_error"],
        )
