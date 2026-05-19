# Lead Processing MVP

Сервіс автоматизованої обробки заявок з лендінгу.

**Стек:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy · SQLite · OpenAI · Telegram

---

## Архітектура та рішення

```
POST /api/leads
  │
  ├─ Pydantic v2 — validate + normalize (email→lowercase, phone→digits, name→capitalize)
  ├─ SQLite/SQLAlchemy — зберігаємо raw payload одразу
  ├─ 202 Accepted → відповідь клієнту
  │
  └─ BackgroundTask (async):
       ├─ зберігаємо нормалізовані поля
       ├─ OpenAI gpt-4o-mini (Structured Outputs) → summary + lead_class + confidence
       ├─ UPDATE leads SET ai_summary=..., lead_class=..., processing_status="done"
       └─ Telegram sendMessage → сповіщення менеджеру
```

**Чому SQLite, а не Google Sheets:**
SQLite дозволяє надійно зберігати raw + normalized payload, статус обробки, помилки та AI-результати в одному місці. Для production вистачить замінити `DATABASE_URL` на PostgreSQL без зміни коду.

**Чому BackgroundTasks, а не sync:**
Клієнт отримує 202 миттєво — незалежно від швидкості LLM (1–3 сек). Це критично для форм на лендінгу.

**Чому Structured Outputs:**
`client.beta.chat.completions.parse()` гарантує валідний JSON з правильними типами — без `json.loads` та try/except навколо парсингу.

---

## Структура проєкту

```
app/
  main.py          — FastAPI endpoints + lifespan
  schemas.py       — Pydantic models (LeadIn, LeadAIResult, LeadOut, LeadDebug)
  models.py        — SQLAlchemy ORM model (leads table)
  db.py            — engine + SessionLocal + get_db
  llm.py           — OpenAI Structured Outputs
  telegram.py      — HTTP sendMessage
  services/
    lead_pipeline.py — повний pipeline в background task
sample_payloads/
  lead_valid.json   — повна заявка
  lead_minimal.json — мінімальна заявка
tests/
  test_normalizers.py     — юніт-тести нормалізації
  test_pipeline_smoke.py  — smoke-тести HTTP endpoints
.env.example
requirements.txt
Procfile           — для Railway
README.md
```

---

## Локальний запуск

### 1. Залежності

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Змінні середовища

```bash
cp .env.example .env
# відредагуй .env: вкажи OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

### 3. Запуск

```bash
uvicorn app.main:app --reload
```

Сервіс доступний на `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`

### 4. Тестовий запит

```bash
curl -X POST http://localhost:8000/api/leads \
  -H "Content-Type: application/json" \
  -d @sample_payloads/lead_valid.json
```

**Відповідь:**
```json
{"id": 1, "status": "accepted", "message": "Заявку прийнято"}
```

### 5. Перевірка результату

```bash
curl http://localhost:8000/debug/leads
```

Через 2–5 секунд у відповіді з'явиться `lead_class`, `ai_summary`, `telegram_sent`.

---

## Деплой на Railway

1. Запуш проєкт на GitHub
2. Відкрий [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
3. Обери репозиторій — Railway автоматично знайде `Procfile`
4. **Variables** → додай:
   ```
   OPENAI_API_KEY=sk-...
   TELEGRAM_BOT_TOKEN=123456789:AAF...
   TELEGRAM_CHAT_ID=123456789
   ```
5. Deploy → отримай публічний URL виду `https://lead-processing-mvp.up.railway.app`

---

## Таблиця leads (схема)

| Колонка | Тип | Опис |
|---|---|---|
| id | int | PK |
| created_at | datetime | час прийому заявки |
| source | str | звідки прийшла заявка |
| processing_status | str | pending / processing / done / error |
| raw_payload_json | text | оригінальний JSON без змін |
| normalized_payload_json | text | нормалізовані дані |
| name / email / phone / company / message | str | поля для запитів |
| ai_summary | text | summary від LLM |
| lead_class | str | hot / warm / cold / junk / manual_review |
| lead_confidence | int | впевненість AI (0–100) |
| ai_model | str | яка модель використовувалась |
| telegram_sent | bool | успішність відправки |
| telegram_error | str | помилка якщо є |

---

## Класифікація лідів

| Клас | Критерії |
|---|---|
| 🔥 hot | чіткий запит + контакт + бюджет або дедлайн |
| 🟡 warm | є інтерес, але запит розмитий або немає бюджету |
| 🔵 cold | загальне питання, мінімум деталей |
| 🗑 junk | спам, тест, нерелевантний запит |
| ⚠️ manual_review | AI не впевнений або LLM-помилка |

---

## Тести

```bash
pytest tests/ -v
```

---

## Endpoints

| Method | Path | Опис |
|---|---|---|
| POST | `/api/leads` | Прийняти заявку (202 Accepted) |
| GET | `/debug/leads` | Останні ліди з AI-результатами |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
