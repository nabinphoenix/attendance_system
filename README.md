# AntimBench

AntimBench is a modular college attendance and CRM platform. The FastAPI backend groups identity, academics, scheduling, attendance, course-completion, CRM, and operations concerns into self-contained modules. The Next.js frontend provides role-oriented workspaces for students, teachers, administrators, coordinators, and parents.

## Backend

Requirements: Python 3.12+, Docker Desktop, and [uv](https://docs.astral.sh/uv/).

```powershell
docker compose up -d postgres
cd backend
Copy-Item .env.example .env   # skip when retaining the generated local development file
# Edit .env with a working PostgreSQL URL and a secure JWT key.
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

The Compose service runs PostgreSQL 17 at `localhost:5433` (container port 5432) with database, user, and password all set to `antimbench`. Port 5433 avoids collisions with commonly installed local PostgreSQL services. Data persists in the named `antimbench_postgres_data` volume. Wait for `docker compose ps` to report the service as healthy before migrating. The checked-in environment template already contains `postgresql://antimbench:antimbench@localhost:5433/antimbench`; use different credentials outside local development.

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

## Attendance vertical-slice demo

Run the seed command above after migrating. It creates an active timetable, one teacher, and four enrolled students and prints their credentials. Sign in as the teacher at `/login`, start the current class, and open its live view. In another browser profile, sign in as a student, paste the displayed QR token at `/student/check-in`, and permit a fresh high-accuracy location reading. QR codes rotate on the backend according to `QR_TOKEN_EXPIRE_SECONDS`; the teacher roster polls every four seconds.

For this hackathon slice, the browser stores the JWT in `localStorage`. This is vulnerable to token theft if an XSS flaw exists. Production deployment should replace it with a same-origin backend-for-frontend that sets a `Secure`, `HttpOnly`, `SameSite` cookie.

## Phase 3 operations

Admins can create and approve dated schedule overrides at `/admin/overrides`. An approved substitute assignment completely transfers start/manage access for that date: the original teacher cannot start or manage the overridden session, while original and effective teacher/room values remain recorded separately. Bulk student CSV onboarding is available at `/admin/imports`; expected headers are `name,email,batch_name,section_name,phone`. Successful accounts receive the temporary password `Welcome123!`, which must be replaced with a reset-token flow before production use. Each row uses a database savepoint, so invalid rows do not roll back valid accounts. Teachers can review their session history from `/teacher/sessions` and open completed roster summaries.
