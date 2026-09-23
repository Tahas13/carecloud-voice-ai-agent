# CareCloud Voice AI Agent — Patient Registration

A voice-based AI agent, reachable at a real U.S. phone number, that registers new patients through natural conversation, persists their demographics to a database, and exposes them through a REST API and a web dashboard.

> **Live demo**
>
> - **Phone number to call:** **+1 (708) 523-1081**
> - **API base URL:** `https://carecloud-api-production-7306.up.railway.app`
> - **Dashboard:** [https://carecloud-api-production-7306.up.railway.app/dashboard](https://carecloud-api-production-7306.up.railway.app/dashboard)
> - **Interactive API docs (Swagger):** [https://carecloud-api-production-7306.up.railway.app/docs](https://carecloud-api-production-7306.up.railway.app/docs)
>
> Deployed on **Railway** (Docker) with **managed PostgreSQL** (private-network only — the database
> is not exposed publicly). No credentials are needed to test the API or dashboard. This is a demo
> system — please do not provide real patient data.

## Architecture

```
 Caller ──PSTN──> Vapi phone number
                    │
                    ▼
        Vapi voice pipeline (Deepgram STT ▸ GPT-4o ▸ TTS)
                    │  tool-calls / end-of-call-report
                    ▼  POST /vapi/webhook  (X-Vapi-Secret)
 ┌──────────────────────────────────────────────────────┐
 │ FastAPI service (Railway)                            │
 │   routers/vapi.py ── tool dispatcher                 │
 │   routers/patients.py ── REST API                    │
 │   routers/dashboard.py ── web UI                     │
 │        │                                             │
 │   services/ (patient_service, call_service)          │
 │   validators.py  ◄── single source of validation     │
 │        │                                             │
 │   PostgreSQL (Railway) / SQLite (local)              │
 │     patients · call_logs                             │
 └──────────────────────────────────────────────────────┘
```

**Separation of concerns:** telephony/STT/TTS live entirely in Vapi; conversation policy lives in one version-controlled prompt ([app/agent/system_prompt.md](app/agent/system_prompt.md)); business logic and validation live in the FastAPI service; persistence is a thin service layer over SQLAlchemy. The voice agent and the REST API share the *same* service layer and the *same* validators, so a value that the phone agent accepts is exactly the value the API would accept.

## Tech stack and why

| Layer | Choice | Justification |
|---|---|---|
| Telephony + voice | **Vapi** | Free U.S. number, managed STT/TTS/turn-taking, native tool-calling into our webhook. Building Twilio+Deepgram+TTS from scratch would spend the 3-hour budget on plumbing instead of conversation quality. |
| LLM | **OpenAI GPT-4o** | Strongest at mid-conversation corrections, spelled-out names ("D-A-V-I-S"), and reliable tool-calling. Temperature 0.4 for warmth without improvisation. |
| Backend | **Python + FastAPI + Pydantic v2** | One set of Pydantic validators serves both the REST API and the voice tools; automatic OpenAPI docs; fast to build well. |
| Database | **PostgreSQL (Railway) / SQLite (local & tests)** | Single `DATABASE_URL` switch. Postgres in production for real persistence across restarts; SQLite locally for zero setup. |
| Hosting | **Railway** | Always-warm container (no cold starts to break mid-call tool calls), managed Postgres, deploy from GitHub. |

## Project layout

```
app/
  main.py              FastAPI app, envelope error handlers, startup + seeding
  config.py            settings from environment variables (nothing hardcoded)
  database.py          engine/session for postgres:// and sqlite://
  models.py            Patient, CallLog (constraints, soft delete, timestamps)
  validators.py        every field rule in one place (shared voice + API)
  schemas.py           Pydantic request/response models + {"data","error"} envelope
  services/            patient_service.py, call_service.py (data access layer)
  routers/             patients.py (REST), vapi.py (webhook), dashboard.py, health.py
  agent/
    system_prompt.md   THE system prompt, with design notes per section
    tools.py           JSON schemas of the 5 agent tools
    assistant.py       full Vapi assistant payload (config as code)
  templates/           dashboard HTML (Jinja2 + Tailwind)
scripts/setup_vapi.py  idempotent: create/update assistant + attach phone number
tests/                 38 pytest tests: API, validators, webhook
```

## Setup

### Local

```bash
git clone <repo-url> && cd carecloud
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in values
uvicorn app.main:app --reload                        # http://localhost:8000
pytest                                               # run the test suite
```

Tables are created automatically on startup and two fictional seed patients (Jane Doe, Carlos Rivera) are inserted when the table is empty.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | prod | Postgres URL on Railway; defaults to local SQLite |
| `VAPI_API_KEY` | for setup script | Private key from the Vapi dashboard |
| `VAPI_WEBHOOK_SECRET` | yes | Shared secret; webhook rejects requests without it (401) |
| `PUBLIC_BASE_URL` | yes | Public HTTPS URL of this service (webhook target) |
| `OPENAI_API_KEY` | optional | Only if attaching your own OpenAI key inside Vapi |
| `SEED_DEMO_DATA` | optional | `true` (default) inserts 2 demo patients when table is empty |
| `LOG_LEVEL` | optional | default `INFO` |

### Deploy (Railway) + wire up the phone number

1. Create a Railway project from this repo; add the **PostgreSQL** plugin (`DATABASE_URL` is injected automatically).
2. Set `VAPI_WEBHOOK_SECRET` (any long random string) and `PUBLIC_BASE_URL` (the Railway domain) on the service.
3. Locally, with `VAPI_API_KEY`, `PUBLIC_BASE_URL`, `VAPI_WEBHOOK_SECRET` in `.env`, run:

   ```bash
   python scripts/setup_vapi.py
   ```

   This creates/updates the assistant from [app/agent/assistant.py](app/agent/assistant.py), attaches it to the account's phone number (creating a free Vapi U.S. number if there is none), and prints the number to call. Re-running it is safe — it updates in place.

## REST API

All responses use a consistent envelope: `{"data": ..., "error": null}` on success, `{"data": null, "error": {"code", "message", "details?"}}` on failure. Status codes: 200 / 201 / 400 / 401 / 404 / 422 / 500.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/patients` | Optional filters: `?last_name=` (case-insensitive), `?date_of_birth=` (MM/DD/YYYY or ISO), `?phone_number=` (any format, normalized) |
| GET | `/patients/{id}` | 422 if not a UUID, 404 if missing or soft-deleted |
| POST | `/patients` | 201 with created record; server-side validation of every field |
| PUT | `/patients/{id}` | Partial update — send only the fields to change |
| DELETE | `/patients/{id}` | Soft delete: sets `deleted_at`, record is retained |

```bash
BASE=https://<your-app>.up.railway.app

# List / filter
curl "$BASE/patients?last_name=Doe"

# Create
curl -X POST "$BASE/patients" -H 'Content-Type: application/json' -d '{
  "first_name":"Maria","last_name":"Garcia","date_of_birth":"04/12/1985",
  "sex":"Female","phone_number":"(305) 555-0142","address_line_1":"789 Palm Ave",
  "city":"Miami","state":"FL","zip_code":"33101"}'

# Partial update
curl -X PUT "$BASE/patients/<uuid>" -H 'Content-Type: application/json' -d '{"city":"Orlando"}'

# Soft delete
curl -X DELETE "$BASE/patients/<uuid>"
```

Validation rules follow the assessment exactly: names 1–50 chars (letters/hyphens/apostrophes), DOB valid and not in the future (MM/DD/YYYY), sex is one of Male/Female/Other/Decline to Answer, phone is a normalized 10-digit U.S. number, state is a valid 2-letter abbreviation (full names accepted and normalized), ZIP is 5-digit or ZIP+4.

## The voice agent

The full prompt is in [app/agent/system_prompt.md](app/agent/system_prompt.md) with commented design notes. Key mechanics:

- **Five tools** (defined in [app/agent/tools.py](app/agent/tools.py), handled in [app/routers/vapi.py](app/routers/vapi.py)):
  - `validate_patient_field` — validates each risky field (DOB, phone, ZIP, state, email) the moment it is spoken; invalid values trigger an immediate, field-specific re-prompt.
  - `lookup_patient_by_phone` — duplicate detection: recognizes returning callers and offers to update instead of re-register.
  - `register_patient` — final save; only callable after a full read-back and explicit "yes". Returns per-field errors, duplicate warnings, or a graceful database-failure message the agent relays aloud.
  - `update_patient` — returning-caller partial updates.
  - `schedule_appointment` — bonus: mock first-appointment booking with a confirmation code.
- **Confirmation before saving** is mandatory in the prompt: the agent reads every field back and only saves after explicit confirmation.
- **Transcripts:** Vapi sends an `end-of-call-report` after each call; we persist transcript, summary, and LLM-extracted structured data in `call_logs`, linked to the patient by phone number — so even dropped calls leave a partial record. The final data payload is also logged to stdout.

### Suggested test script for reviewers

1. Call the number; register with normal, conversational phrasing.
2. Mid-call, correct something: *"Actually, my last name is spelled D-A-V-I-S."*
3. Give an invalid DOB (a future date) — the agent re-asks for just the DOB.
4. Answer out of order (give your phone number when asked for DOB) — it slots values correctly.
5. Say *"Can we start over?"* — it wipes and restarts.
6. Confirm at the read-back; hear *"You're all set, [name]"*; optionally book an appointment.
7. Verify persistence: `GET /patients?last_name=<yours>` or open `/dashboard`.
8. Call again from the same number path: give the same phone number — the agent recognizes you and offers to update.
9. Say *"Hablo español"* — the agent switches to Spanish.

## Edge cases & resilience

| Scenario | Behavior |
|---|---|
| Invalid DOB / phone / ZIP / state | Caught by `validate_patient_field` at capture time and again server-side at save; agent re-prompts for that field only |
| Caller corrects a field | Prompt rules: replace value, confirm briefly, spelled-out letters are authoritative |
| Caller wants to start over | Prompt rule: discard everything, restart from first name |
| Call drops mid-conversation | `end-of-call-report` still fires; partial structured data + transcript saved as an `incomplete` call log |
| Database write fails | Tool returns a graceful error string; the agent apologizes aloud and offers a retry — never silence |
| Duplicate phone number | Agent offers update-instead-of-create; explicit override available |
| Webhook probing | Requests without the correct `X-Vapi-Secret` get 401 |
| 30 s of silence / runaway call | `silenceTimeoutSeconds: 30`, `maxDurationSeconds: 900` |

## Security

- No secrets in source — everything via environment variables (`.env.example` documents them; `.env` is gitignored).
- Webhook authenticated with a shared secret header.
- Server-side validation and basic sanitization on every input; the API never trusts the voice agent.
- Not HIPAA-compliant by design — the assessment explicitly scopes this out; no real patient data should be used.

## Known limitations & trade-offs

- **`create_all` instead of Alembic migrations** — right call for a 3-hour build; migrations are the first thing to add for a real system.
- **Mock appointment scheduling** — returns fabricated slots and confirmation codes; no calendar behind it.
- **Spanish support is best-effort** — Deepgram multi-language + prompt instruction; not separately QA'd like the English flow.
- **Dashboard is read-only** and unauthenticated (demo scope); the REST API is likewise open for reviewer testing.
- **Phone numbers are stored as bare 10 digits** — no international support (assessment scope is U.S. only).
- **One shared Vapi number** — free-tier Vapi numbers are inbound-only, U.S. only.

## Next steps (if given more time)

- Alembic migrations; API pagination; auth (API keys) for write endpoints.
- Real scheduling integration and SMS confirmation (Twilio) after registration.
- Post-call quality evals: automatic scoring of transcripts against the collected record.
- Voicemail/no-input recovery flows and mid-call resumption for dropped calls (call back and continue).
- Redact PII from logs; encrypt at rest beyond provider defaults.
