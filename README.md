# AntimBench

> Phase 5 adds role-scoped CSV/PDF reports, durable notifications, an audit viewer, parent access, and a college-wide admin dashboard.

AntimBench is a modular college attendance and CRM platform. The FastAPI backend groups identity, academics, scheduling, attendance, course-completion, CRM, and operations concerns into self-contained modules. The Next.js frontend provides role-oriented workspaces for students, teachers, administrators, coordinators, and parents.

## Backend

Requirements: Python 3.12+, a native PostgreSQL installation, and [uv](https://docs.astral.sh/uv/).

Create the database and a local application user in PostgreSQL (using psql or pgAdmin):

```sql
CREATE DATABASE antimbench;
CREATE USER antimbench_user WITH PASSWORD 'choose-a-local-password';
GRANT ALL PRIVILEGES ON DATABASE antimbench TO antimbench_user;
```

Then configure `backend/.env` with `DATABASE_URL=postgresql://antimbench_user:<password>@localhost:5432/antimbench` and run:

```powershell
cd backend
Copy-Item .env.example .env   # skip when retaining the generated local development file
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

Run durable notification delivery in a second terminal after configuring SMTP:

```powershell
cd backend
uv run python -m app.workers.worker
```

In production, the Elastic Beanstalk deployment installs this worker as the
always-on `antimbench-notification-worker` systemd service. Configure the
GitHub `production` environment with these Actions secrets:

- `SMTP_USERNAME`: the Gmail/Google Workspace sender address
- `SMTP_PASSWORD`: a Google app password, never the normal account password

The deployment uses `smtp.gmail.com` on port `587` by default. These optional
GitHub Actions variables can override the defaults:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_FROM_EMAIL` (defaults to `SMTP_USERNAME`)

On each deployment, the workflow copies the configured values into Elastic
Beanstalk environment properties and restarts the worker. GitHub Secrets store
the credentials; the deployed systemd service is what continuously processes
the durable email queue. Guardians without linked user accounts and real email
addresses cannot receive attendance-support alerts and are recorded as failed
deliveries rather than Gmail configuration failures.

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

### Testing on a phone

`npm run dev` listens on the local network and proxies browser API requests through Next.js. Keep the computer and phone on the same Wi-Fi network, then open `http://<computer-LAN-IP>:3000` on the phone (find the LAN IP with `ipconfig`). Do not use `localhost` on the phone: it refers to the phone itself. If Windows asks, allow Node.js through the private-network firewall.

Mobile camera and GPS access for QR attendance require HTTPS. For local testing, run `npm run dev:https` and open `https://<computer-LAN-IP>:3000`; accept the local development certificate on the phone. For deployment, use a trusted HTTPS certificate and never rely on the self-signed development certificate.

## Structure

- `backend/app/core`: settings, database sessions, security, and dependencies
- `backend/app/modules`: independently organized business modules
- `backend/app/workers`: durable notification worker and job handlers
- `backend/migrations`: Alembic environment and generated revisions
- `backend/tests`: module-level test suites
- `frontend/app`: App Router pages grouped by role
- `frontend/components`: shared UI and attendance/QR components
- `frontend/lib`: API, authentication, and geolocation helpers
- `frontend/types`: shared frontend domain interfaces

Secrets belong only in ignored `.env` and `.env.local` files. Commit the corresponding `.example` templates instead.

## Initial data

Run the seed command above after migrating to create the administrator login only. No academic, timetable, student, or attendance sample data is created; add your own program, batch, section, subjects, teachers, and routine from the admin workspace.

Browser logins now establish a `HttpOnly`, `SameSite=Lax` session cookie; the frontend never stores the token in `localStorage`. Set `AUTH_COOKIE_SECURE=true` when serving the application over HTTPS in production. Login responses retain a bearer token only for documented non-browser API clients.

## Phase 3 operations

Admins can create and approve dated schedule overrides at `/admin/overrides`. An approved substitute assignment completely transfers start/manage access for that date: the original teacher cannot start or manage the overridden session, while original and effective teacher/room values remain recorded separately. Bulk student CSV onboarding is available at `/admin/imports`; expected headers are `name,email,batch_name,section_name,phone`. Successful imports create accounts with the temporary password `Welcome123!`; admins can send a hashed, single-use password-setup link from `/admin/students` so each student replaces it securely. Each row uses a database savepoint, so invalid rows do not roll back valid accounts. Teachers can review their session history from `/teacher/sessions` and open completed roster summaries.

## Phase 4 intervention workflow

Course plans track planned and finalized sessions. Finalization increments the matching canonical module-offering/batch plan exactly once (legacy subject plans remain supported for historical records). Admins can request the first conflict-free one-hour makeup slot within the next 14 days and approve it as an additional routine occurrence at `/admin/course-completion`.

Attendance analytics are exposed under `/api/v1/analytics`. Risk evaluation requires at least `MINIMUM_OBSERVATIONS` finalized observations and compares subject attendance against `ATTENDANCE_THRESHOLD_PERCENT`. Re-running evaluation refreshes the active case rather than creating duplicates. PostgreSQL enforces this with the partial unique index `uq_active_case` for open/in-progress cases. Coordinators manage assignment, chronological interactions, resolution, and closure from `/coordinator/cases`; closing requires a note.
