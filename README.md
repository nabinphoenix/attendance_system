# AntimBench

AntimBench is a modular college attendance and CRM platform. The FastAPI backend groups identity, academics, scheduling, attendance, course-completion, CRM, and operations concerns into self-contained modules. The Next.js frontend provides role-oriented workspaces for students, teachers, administrators, coordinators, and parents.

## Backend

Requirements: Python 3.12+, PostgreSQL, and [uv](https://docs.astral.sh/uv/).

```powershell
cd backend
Copy-Item .env.example .env   # skip when retaining the generated local development file
# Edit .env with a working PostgreSQL URL and a secure JWT key.
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

The API health endpoint is `http://localhost:8000/health`; interactive documentation is at `/docs`. Run tests with `uv run pytest` and create the initial database migration with `uv run alembic revision --autogenerate -m "initial schema"` once PostgreSQL is available.

## Frontend

Requirements: Node.js 20+ and npm.

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Role routes use explicit prefixes such as `/student/dashboard`, `/teacher/sessions`, and `/admin/dashboard`; route groups organize their source without producing ambiguous duplicate URLs.

## Structure

- `backend/app/core`: settings, database sessions, security, and dependencies
- `backend/app/modules`: independently organized business modules
- `backend/app/workers`: local queue starter and job handlers
- `backend/migrations`: Alembic environment and generated revisions
- `backend/tests`: module-level test suites
- `frontend/app`: App Router pages grouped by role
- `frontend/components`: shared UI and attendance/QR components
- `frontend/lib`: API, authentication, and geolocation helpers
- `frontend/types`: shared frontend domain interfaces

Secrets belong only in ignored `.env` and `.env.local` files. Commit the corresponding `.example` templates instead.
