# AntimBench

AntimBench is a college attendance, academic-routine, student-support, and reporting system. It provides role-based workspaces for administrators, teachers, students, coordinators, and guardians. The application combines routine management, QR attendance, geofence checks, student onboarding, intervention cases, exports, and email notifications in one system.

## What the system does

- Administrators maintain programmes, intakes, batches, sections, modules, offerings, rooms, class types, and time slots.
- Administrators import students and routine data from CSV/XLSX files, review import errors, and download templates.
- A successful student import creates a student account and queues a secure account-setup email. The student chooses their own password through a single-use link before signing in.
- Teachers start a class session, capture a campus location, show a rotating QR code and classroom code, review exceptions, and finalize attendance.
- Students scan the QR code, provide a fresh device location, enter the teacher's classroom code, and view their own attendance and reports.
- The system creates student-support cases and emails students automatically when subject/module attendance falls below the configured threshold.
- Administrators and staff can inspect analytics, intervention cases, audit logs, course completion, and CSV/PDF exports.

## Architecture

```text
Next.js + React frontend
        |
        | Same-origin API proxy / HTTPS browser session
        v
FastAPI backend (REST API, JWT cookie/bearer authentication)
        |
        +-- PostgreSQL on AWS (SQLAlchemy models + Alembic migrations)
        +-- SMTP/Gmail worker (durable notifications table)
        +-- Optional S3 profile-image storage
```

The frontend is in `frontend/`; the backend is in `backend/`. FastAPI registers modular routers in `backend/app/main.py`. The major backend modules are `identity`, `academic`, `scheduling`, `attendance`, `analytics`, `course_completion`, `crm`, and `operations`.

## User roles

| Role | Main responsibilities |
| --- | --- |
| Administrator | Academic setup, imports, users, routines, overrides, reports, notifications, audit logs, cases, and system-wide analytics. |
| Teacher | Starts sessions, displays QR/classroom codes, takes manual attendance, resolves exceptions, finalizes classes, and views assigned-class analysis. |
| Student | Signs in, completes QR/geofence attendance, views routine, dashboard, attendance summary, and reports. |
| Coordinator | Reviews and manages student-support cases. |
| Parent/Guardian | Views linked student information and applicable notifications. |

## Main request flow

1. A browser signs in with `/api/v1/auth/login`; FastAPI verifies the bcrypt password hash and creates a signed JWT session cookie.
2. The frontend calls role-protected REST endpoints through Axios.
3. FastAPI validates the token, checks the role, reads/writes PostgreSQL through SQLAlchemy, and records important actions in `audit_logs`.
4. Any email is first written as a durable `notifications` row. The separate worker reads pending rows and delivers them through SMTP.
5. A teacher's finalization of a class persists attendance records, completes the class session, updates course-plan progress, and runs the low-attendance evaluation.

## Database design

The current SQLAlchemy metadata contains **37 application tables**. Alembic migrations in `backend/migrations/versions/` create and evolve this schema. PostgreSQL is the production database; SQLite is used by the automated tests.

### Identity and people

| Table | Purpose |
| --- | --- |
| `users` | Login identity, name, email, bcrypt password hash, role, active state, and optional profile-image key. |
| `students` | Student profile, section, roll number, email, and optional link to `users`. |
| `teachers` | Teacher profile linked one-to-one with a user and employee code. |
| `guardians` | Guardian/parent records linked to students and optionally to a user account. |
| `student_invitations` | Hashed, single-use activation/password-setup tokens with status, purpose, and expiry. |

### Academic structure and routines

| Table | Purpose |
| --- | --- |
| `programs` | Academic programmes. |
| `intakes` | Programme intake/cohort, code, and start date. |
| `batches` | Academic batches linked to programmes. |
| `sections` | Student sections linked to batches and optionally intake/semester. |
| `modules` | Canonical academic modules: code, title, credits, and semester. |
| `module_offerings` | Makes a module active for a particular intake, batch, semester, and set of sections. |
| `module_offering_sections` | Many-to-many membership between module offerings and sections. |
| `subjects` | Legacy subject records retained for historic timetable data. |
| `student_subject_enrollments` | Many-to-many enrollment between students and legacy subjects. |
| `class_types` | Reusable class type values such as Lecture or Practical. |
| `time_slots` | Reusable start/end time ranges. |
| `blocks` | College buildings/blocks. |
| `rooms` | Room, capacity, type, optional coordinates, and optional geofence radius. |
| `routine_entries` | Canonical recurring class: module, section, class type, teacher, room, day, and time slot. |
| `routine_entry_sections` | Additional sections attending one physical combined routine. |
| `routine_pending_sections` | Combined section references that could not yet be resolved during import. |
| `timetable_entries` | Legacy timetable source retained for compatibility with earlier records. |
| `schedule_overrides` | Approved/rejected dated changes to room, teacher, times, cancellation, or makeup sessions. |

### Attendance and classroom verification

| Table | Purpose |
| --- | --- |
| `class_sessions` | A concrete active/completed occurrence of a routine or legacy timetable entry. |
| `attendance_records` | One attendance result per student per class session: present, late, absent, leave, or bunk. |
| `attendance_changes` | Reasoned manual correction history for attendance records. |
| `attendance_challenges` | Rotating QR-version data plus a hashed/encrypted classroom code. |
| `pending_attendance_verifications` | Short-lived student check-in verification after a QR scan. |
| `check_in_attempts` | Accepted, pending, confirmed, or rejected check-in/audit evidence. |
| `leave_requests` | Student leave requests used when finalizing attendance. |

### Reporting, interventions, and operations

| Table | Purpose |
| --- | --- |
| `course_plans` | Planned versus conducted sessions for a subject/module offering and batch. |
| `makeup_suggestions` | Proposed makeup classes to address course-delivery shortfalls. |
| `student_cases` | Support/intervention cases, including low-attendance cases and priority. |
| `case_interactions` | Notes, communication channel, staff member, and outcome for a case. |
| `import_jobs` | File name, type, success/failure counts, and row-level import errors. |
| `notifications` | Durable email queue and delivery status: pending, sent, or failed. |
| `audit_logs` | Who performed an important action, what changed, and when. |

### Important relationships

```text
Program -> Intake / Batch -> Section -> Student -> User
Module -> ModuleOffering <-> Section
RoutineEntry -> ClassSession -> AttendanceRecord -> Student
ClassSession -> AttendanceChallenge -> PendingAttendanceVerification
Student + module/subject -> StudentCase -> CaseInteraction
Any business event -> Notification -> SMTP worker
```

Foreign keys, unique constraints, indexes, and application validation protect identity, enrollment, routine, and attendance relationships. For example, `attendance_records` is unique for `(class_session_id, student_id)`, preventing duplicate attendance for the same class.

## Authentication and security

- Passwords are hashed with **bcrypt** through Passlib; plaintext passwords are never stored in the database.
- FastAPI issues signed JWT access tokens using `python-jose`; browser sessions are held in an HTTP-only cookie.
- Role dependencies protect administrator, teacher, student, coordinator, and parent endpoints.
- Student-import welcome emails use a single-use password-setup token. The token hash is stored in `student_invitations`; a successful delivery redacts the raw setup link from the queued notification record.
- QR tokens are signed JWTs. The classroom code is HMAC-hashed for comparison and encrypted at rest for the teacher to reveal.
- Profile-image files are validated with Pillow and can use private S3 storage through Boto3.
- CORS origins, cookie security, database URL, JWT secret, and SMTP secrets are environment variables, not source code.

## Dynamic QR, classroom code, timer, and location check

This project uses **geolocation/geofencing**, not a visual map SDK. There is no Mapbox, Leaflet, Google Maps, or rendered map package in the application. The browser gets coordinates from the device and the backend calculates the distance to the teacher-captured classroom location using the Haversine formula.

### Teacher flow

1. The teacher starts a scheduled session and the browser sends latitude, longitude, accuracy, radius, check-in window, and QR rotation preference.
2. The session stores the teacher's captured location and the effective teacher/room after any approved override.
3. The backend creates a signed QR JWT, a random nonce, and a classroom code. The QR and code are tied to the current session/version.
4. The teacher interface renders the QR with `qrcode.react`; it can be displayed full-screen.
5. On every rotation, the earlier challenge is revoked and still-pending verifications from the previous rotation are invalidated.

### Student flow

1. The student scanner loads `html5-qrcode` only when needed and reads the teacher's QR token.
2. Browser `navigator.geolocation.watchPosition()` asks for a fresh high-accuracy coordinate. The client waits up to 10 seconds and accepts a reading early when accuracy is at most 100 metres.
3. The backend verifies the signed QR, expiry, current QR version/nonce, student eligibility, location accuracy, and the Haversine distance against the session geofence.
4. A successful QR/location check creates a short-lived pending verification. The student enters the spoken classroom code to finish attendance.
5. The backend records a `present` QR/geofence attendance record only after the code matches. Failed, expired, duplicate, or out-of-bound attempts are audited.

### Default timer and safety settings

| Setting | Default | Meaning |
| --- | ---: | --- |
| `ATTENDANCE_CHALLENGE_ROTATION_SECONDS` | 20 seconds | QR token and classroom-code rotation period. |
| `ATTENDANCE_SELF_CHECKIN_WINDOW_MINUTES` | 15 minutes | Period after session start when self check-in is open. |
| `ATTENDANCE_VERIFICATION_TIMEOUT_SECONDS` | 12 seconds | Maximum time between QR validation and classroom-code confirmation. |
| `ATTENDANCE_MAX_CODE_ATTEMPTS` | 3 | Maximum code attempts before verification is rejected. |
| `GEOFENCE_RADIUS_METERS` | 150 m | Default campus/classroom boundary when no session-specific radius is supplied. |
| `GEOLOCATION_MAX_ACCURACY_METERS` | 100 m | Maximum accepted device accuracy. |

Teachers can still review pending location/code exceptions and record manual attendance where appropriate.

## Bulk import

The import API accepts CSV or XLSX. An XLSX file must contain exactly one worksheet named **`Timetable`**. Each row is handled in a database savepoint, so invalid rows do not roll back successful rows. The `import_jobs` table preserves the outcome and row errors.

### Student import

Endpoint: `POST /api/v1/imports/students`

| Column | Required | Notes |
| --- | --- | --- |
| `name` | Yes | Student display name. |
| `email` | Yes | Unique email address; also becomes the sign-in email. |
| `batch_name` | Yes | Must match an existing batch. |
| `section_name` | Yes | Must match an existing section in that batch. |
| `phone` | No | Creates a guardian contact when supplied. |
| `roll_number` | No | Uses an import-generated roll number when omitted. |

```csv
name,email,batch_name,section_name,phone,roll_number
Student Name,student@example.com,2026,A1,9800000000,A1-001
```

A successful row creates a `users` row, `students` row, optional `guardians` row, `student_invitations` row, and pending `notifications` row. The worker sends a welcome email with the public application URL and a one-time setup link.

### Teacher timetable import

Endpoint: `POST /api/v1/academic/teachers/{teacher_id}/timetable/import`

```csv
intake_code,semester,sections,day,start_time,end_time,module_code,class_type,block,room
NPT3F2509IT,SEM VI,A3|A4,SUN,08:30,09:30,CT004-3-3,Lecture,Block B,Machapuchare-L04
```

### Section routine import

Endpoint: `POST /api/v1/academic/sections/{section_id}/routine/import`

```csv
day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room
SUN,08:30,09:30,A3|A4,CT004-3-3,Advanced Database Systems,Lecture,teacher@example.com,Block B,Machapuchare-L04
```

Routine imports validate the intake, semester, module code/title, class type, teacher email, block, room, time slot, module offering, combined sections, and conflicts before creating or merging a routine.

## Exports and reports

### Export formats

- **Attendance CSV/PDF**: date range plus optional student, section, batch, or teacher scope. Students are restricted to their own records.
- **Case CSV/PDF**: administrator export of student-support cases with optional status/date filters.
- **Course completion CSV**: planned sessions, conducted sessions, and deficit by course and batch.
- **Teacher timetable export**: downloadable teacher routine data.

`pandas` creates tabular data and CSV output. PDFs are first rendered with **WeasyPrint** from HTML/CSS; **ReportLab** is the fallback when WeasyPrint cannot render.

### Analytics implementation

The analytics service joins completed `class_sessions` with `attendance_records`, then groups results by canonical module or legacy subject. `present` and `late` count as attended; other statuses count as not attended.

| Report | Audience | What it shows |
| --- | --- | --- |
| My attendance summary/report | Student | Overall and module/subject attendance, daily records, class type, and CSV export. |
| Teacher attendance analysis | Teacher | Only assigned modules/sections/classes, with module, section, class-type, and date filters. |
| Section attendance summary | Admin/teacher | Per-student percentage for a section. |
| College dashboard | Admin | Overall attendance, open case priorities, pending overrides, and pending makeup suggestions. |
| At-risk students | Admin | Students below the configured attendance threshold. |
| Selective absence | Admin/teacher | Students who attended some courses but missed others on a selected day. |

### Low-attendance automation

`ATTENDANCE_THRESHOLD_PERCENT` defaults to **75** and `MINIMUM_OBSERVATIONS` defaults to **4** completed classes. When a teacher finalizes a class, the service recalculates attendance. If a student first falls below the threshold for a module/subject, it creates one active `student_cases` record and queues a student email. The email includes the module/subject name, module code, class type, current percentage, and threshold. A guardian alert is also queued for linked guardians.

The unique active-case design prevents an email every time an evaluation runs for the same ongoing issue.

## Email and notification service

Email delivery is durable rather than being sent during the browser request:

```text
Import / password setup / risk evaluation
        -> notifications.status = pending
        -> notification worker polls PostgreSQL
        -> SMTP STARTTLS login and send
        -> notifications.status = sent or failed
```

The worker is `python -m app.workers.worker`. It polls pending notifications every 5 seconds by default and processes up to 100 rows per batch. In AWS Elastic Beanstalk, the deployment hook registers it as the always-on `antimbench-notification-worker` systemd service.

| Variable | Purpose |
| --- | --- |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server, normally `smtp.gmail.com` and `587` for Gmail/Google Workspace. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP sender and Google app password. Never use the normal Gmail password. |
| `SMTP_FROM_EMAIL` | Sender address shown to recipients. |
| `FRONTEND_URL` | Public student website used in account-setup links. |
| `NOTIFICATION_WORKER_POLL_SECONDS` / `NOTIFICATION_WORKER_BATCH_SIZE` | Worker scheduling controls. |

For a live dashboard test, import one test student with an inbox you control, or use **Admin -> Students** to select an existing student and choose **Email selected**. Check the notification list/API for `pending`, `sent`, or `failed`. Do not email passwords; the one-time setup link is the supported password workflow.

## Main libraries

### Backend

| Library | Use in this project |
| --- | --- |
| FastAPI + Uvicorn | REST API, dependency injection, validation responses, and ASGI serving. |
| Pydantic + pydantic-settings | Request/response schemas and typed `.env` configuration. |
| SQLAlchemy + psycopg2-binary | ORM/database access and PostgreSQL driver. |
| Alembic | Versioned database migrations. |
| Passlib + bcrypt | Password hashing and verification. |
| python-jose + cryptography/Fernet | JWT authentication, signed QR tokens, encryption, and secure comparisons. |
| pandas + OpenPyXL | CSV/XLSX parsing, templates, data frames, and CSV exports. |
| python-multipart | Multipart file uploads for CSV/XLSX imports and profile-image uploads. |
| Jinja2 + WeasyPrint + ReportLab | HTML report construction and PDF generation with fallback. |
| email-validator | Pydantic email validation. |
| Python `smtplib` + `email.message` | SMTP STARTTLS email delivery; standard-library modules. |
| Boto3 + Pillow | Optional S3 profile image storage and safe image validation. |
| qrcode | Declared for server-side QR asset generation; live teacher QR rendering currently uses `qrcode.react` in the frontend. |
| pytest + httpx | Automated backend/API tests. |

### Frontend

| Library | Use in this project |
| --- | --- |
| Next.js + React + TypeScript | Role-based web application and pages. |
| Axios | Authenticated calls to FastAPI through the same-origin proxy. |
| html5-qrcode | Camera QR scanning for student check-in. |
| qrcode.react | Teacher QR-code display. |
| Recharts | Dashboard and analytics charts. |
| Tailwind CSS + PostCSS + Autoprefixer | Responsive UI styling. |
| ESLint | Frontend quality checks. |

## Configuration and deployment

Production uses AWS Elastic Beanstalk for the backend and PostgreSQL in AWS. The deployment workflow applies the version, runs Alembic migrations, configures SMTP/environment values, and restarts both the API and notification worker. The frontend URL in this deployment is `https://antimbench-https-proxy.vercel.app` unless an environment variable overrides it.

```env
DATABASE_URL=postgresql://USER:URL_ENCODED_PASSWORD@HOST:5432/antimbench
JWT_SECRET_KEY=replace-with-a-long-random-secret
AUTH_COOKIE_SECURE=true
FRONTEND_URL=https://antimbench-https-proxy.vercel.app
CORS_ORIGINS=["https://antimbench-https-proxy.vercel.app"]
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=sender@example.com
SMTP_PASSWORD=google-app-password
SMTP_FROM_EMAIL=sender@example.com
```

Do not commit real database credentials, SMTP passwords, AWS credentials, or JWT secrets.

## Local development

### Backend

```powershell
cd backend
Copy-Item .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

Run the notification worker in another terminal:

```powershell
cd backend
uv run python -m app.workers.worker
```

### Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Useful checks:

```powershell
cd backend
uv run pytest

cd ../frontend
npm.cmd run lint
npm.cmd run build
```

## Project layout

```text
backend/
  app/core/                 configuration, database, security, dependencies
  app/modules/              domain modules and API routers
  app/workers/              durable notification worker and SMTP job
  migrations/versions/      Alembic database history
  tests/                    API and workflow tests
frontend/
  app/                      Next.js route pages by user role
  components/               reusable UI, QR, onboarding, and dashboard components
  lib/                      Axios client and geolocation helper
import_templates/           example CSV templates
```

For a detailed operator walkthrough of imports, routine validation, and student onboarding, see [BULK_IMPORT_GUIDE.md](BULK_IMPORT_GUIDE.md). For AWS deployment information, see [DEPLOYMENT.md](DEPLOYMENT.md).
