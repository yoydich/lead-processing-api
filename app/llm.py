import os
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

Відповідай ТІЛЬКИ валідним JSON без markdown та коментарів:
{"summary":"...","lead_class":"...","confidence":0-100,"missing_fields":[],"reasoning_tags":[]}

--- FEW-SHOT ПРИКЛАДИ ---

Приклад 1 — HOT:
Ім'я: Марина Коваль | Email: marina@nova.com | Телефон: 380671234567
Компанія: Nova Digital | Повідомлення: Потрібна таргетована реклама Facebook+Instagram для інтернет-магазину взуття. Бюджет 30к грн/міс, хочемо стартувати з 1 червня. Можна зустріч наступного тижня?
→ {"summary":"Марина з Nova Digital шукає таргет Facebook+Instagram для e-commerce взуття з бюджетом 30к/міс та чітким дедлайном старту.","lead_class":"hot","confidence":96,"missing_fields":[],"reasoning_tags":["budget_confirmed","deadline_set","demo_requested","ecommerce"]}

Приклад 2 — WARM:
Ім'я: Андрій | Email: andrey_biz@ukr.net | Телефон: —
Компанія: — | Повідомлення: Цікавить просування в соцмережах для нашого кафе. Поки що вивчаємо варіанти.
→ {"summary":"Власник або менеджер кафе цікавиться SMM, але на стадії дослідження — немає бюджету, дедлайну та контактного телефону.","lead_class":"warm","confidence":78,"missing_fields":["phone","company","budget"],"reasoning_tags":["exploring_options","food_industry","no_budget"]}

Приклад 3 — COLD:
Ім'я: — | Email: — | Телефон: —
Компанія: — | Повідомлення: привіт скільки коштує реклама
→ {"summary":"Анонімний запит про вартість реклами без жодних контактів, деталей бізнесу або наміру — виключно інформаційний інтерес.","lead_class":"cold","confidence":88,"missing_fields":["name","email","phone","company","budget"],"reasoning_tags":["no_contact","price_inquiry_only","anonymous"]}

Приклад 4 — JUNK:
Ім'я: test | Email: test@test.com | Телефон: 000
Компанія: test | Повідомлення: test 123 asdfgh
→ {"summary":"Тестова або порожня заявка — всі поля містять плейсхолдери, без реального наміру.","lead_class":"junk","confidence":99,"missing_fields":[],"reasoning_tags":["test_data","placeholder_values","no_intent"]}

Приклад 5 — JUNK (спам):
Ім'я: John SEO | Email: promo@seoking.biz | Телефон: —
Компанія: SEO King | Повідомлення: We offer SEO services and backlinks for your website. Best prices! Contact us today.
→ {"summary":"Спам-заявка від SEO-компанії, яка рекламує власні послуги через форму — не цільовий лід.","lead_class":"junk","confidence":98,"missing_fields":[],"reasoning_tags":["spam_signal","outbound_offer","english_only"]}

Приклад 6 — MANUAL REVIEW (суперечливі сигнали):
Ім'я: Олексій Гриценко | Email: — | Телефон: 380501111111
Компанія: ТОВ Альфа | Повідомлення: Нам потрібна допомога з діджитал, бюджет великий, терміново. Але ми вже працюємо з кількома агентствами і не впевнені чи потрібне ще одне.
→ {"summary":"Лід з бюджетом та терміновістю, але явно не впевнений у необхідності нового агентства — висока невизначеність незважаючи на позитивні сигнали.","lead_class":"manual_review","confidence":52,"missing_fields":["email"],"reasoning_tags":["budget_signal","urgency","competing_agencies","uncertainty"]}
"""


def analyze_lead(lead: LeadIn) -> LeadAIResult:
    """
    Call OpenRouter to analyze and classify a lead.
    Uses Chat Completions with JSON mode + few-shot examples.
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
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return LeadAIResult.model_validate_json(content)

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return LeadAIResult(
            summary="Не вдалося проаналізувати заявку автоматично.",
            lead_class="manual_review",
            confidence=0,
            missing_fields=[],
            reasoning_tags=["llm_error"],
        )
