# AI administrative assistant

The assistant is a LangGraph workflow for the attendance system. It uses cloud providers only; it does not require Ollama or a downloaded local model.

## Configure providers

Add only the providers you intend to use to `backend/.env`. The order controls fallback: if Groq is unavailable or rate-limited, OpenRouter is tried, then Gemini. Leave a key or model blank to skip that provider.

```env
AI_ENABLED=true
AI_PROVIDER_ORDER=groq,openrouter,gemini

AI_GROQ_API_KEY=your_groq_key
AI_GROQ_MODEL=llama-3.1-8b-instant

AI_OPENROUTER_API_KEY=your_openrouter_key
AI_OPENROUTER_MODEL=provider/model-id-you-selected

AI_GEMINI_API_KEY=your_gemini_key
AI_GEMINI_MODEL=gemini-2.5-flash
```

Choose the exact model IDs available to each account at deployment time. Keys stay in the backend environment and must never be added to frontend variables, source code, or version control.

After configuring the service:

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Available capabilities

An administrator can ask the assistant to:

- Search programs, batches, intakes, sections, dated cohort semesters, and students.
- Read a student or section attendance summary and list at-risk students.
- Look up scheduled room availability by block, including approved room moves, cancellations, and makeup classes. For example: "Which room is available now in Block A?" The server defaults to the current Nepal campus date and time (Asia/Kathmandu, UTC+05:45); explicit dates and times use YYYY-MM-DD and HH:MM. Availability reflects the timetable, not physical occupancy sensors.
- Prepare a program, batch, intake, section, or dated cohort-semester creation.
- Preview and apply one valid intake/batch semester promotion, including section mapping and held students.

Every write is a proposal first. The proposal displays its exact data, then the same administrator must confirm within the configured expiry period. Confirmation revalidates the data in the current transaction, applies the ordinary domain service, and writes audit events.

## Security boundaries

- The LLM has no database credential, database session, raw SQL tool, filesystem tool, or API key access.
- The browser only talks to the FastAPI backend. Provider calls originate there; provider keys are never returned to the browser.
- `/api/v1/agent/*` is restricted to the existing `admin` role.
- Approval tokens are random, stored only as hashes, tied to the requesting administrator, short-lived, and one-use.
- The assistant has no delete, account/password, attendance-marking, notification-sending, or export tool.
- Only the user prompt and the minimum tool result needed to answer it are sent to the selected provider. Promotion previews stop before another model call, so the roster preview is returned directly to the administrator instead of being sent back to the model.
- Provider data-retention terms differ. Use provider privacy controls and account settings appropriate to your institution before production use.

The current implementation intentionally has no persistent conversation memory. A browser refresh starts a new conversation and avoids retaining extra student data in the application.
