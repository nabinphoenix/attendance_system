# AntimBench Current-State Audit

> ## Validation update — 2026-08-14
>
> This addendum supersedes the earlier claims in this report that the operational tables were empty, the native database was at migration `9647971e5956`, the coordinator account was unavailable, or the listed audit events were missing. It records subsequent live validation against the native PostgreSQL instance at `localhost:5432/antimbench`; no Docker service was used.
>
> - Alembic head is now `b9ae91e2c103` (`timetable_entries.class_type`).
> - The full backend suite passes: **16 passed**. Frontend TypeScript validation passes.
> - Live verification completed for academic setup, teacher/session creation, timetable retrieval, substitute overrides, QR check-in, roster update, finalization, attendance correction, course plan and makeup approval, CSV import, risk evaluation, case assignment/interaction/closure, user deactivation/reactivation, dashboard totals, and audit-log retrieval.
> - The verified substitute assignment made the session visible to the substitute and excluded the original teacher.
> - Audit writes now cover signup, academic setup creation, timetable creation, override creation, session start, QR issuance, successful check-in, finalization, course plan creation, makeup suggestion creation/decision, and case interaction creation.
>
> Final verified live row counts:
>
> | Table | Rows |
> | --- | ---: |
> | `users` | 14 |
> | `students` | 6 |
> | `teachers` | 4 |
> | `programs`, `batches`, `sections`, `subjects` | 2 each |
> | `timetable_entries` | 3 |
> | `schedule_overrides` | 2 |
> | `class_sessions` | 6 |
> | `attendance_records` | 8 |
> | `attendance_changes` | 1 |
> | `course_plans` | 1 |
> | `makeup_suggestions` | 1 |
> | `student_cases` | 1 |
> | `case_interactions` | 2 |
> | `import_jobs` | 1 |
> | `audit_logs` | 24 |
> | `notifications` | 7 |
>
> Remaining production hardening concerns: browser-camera QR scanning, password-reset/forced-reset flows, real SMTP delivery, automatic rather than manually triggered risk evaluation, and replacing `localStorage` JWT storage with a secure cookie/BFF design.

Initial audit performed 2026-08-14 against the running local services and the database configured in `backend/.env`. It was non-mutating; the dated validation update above records the later authorized live verification records.

Status definitions used below:

- **FULLY WORKING**: exercised successfully against the live configured service in this audit.
- **PARTIALLY WORKING**: code and/or isolated integration tests exist, but an important part is untested in the live system, unavailable because live data is absent, or has a concrete limitation.
- **NOT IMPLEMENTED**: no functional implementation exists for the requested capability.

## 1. Database connectivity — verified

`backend/.env` configures **PostgreSQL**, not SQLite. The running SQLAlchemy engine reported `postgresql`, host `localhost`, port `5432`, database `antimbench`.

`uv run alembic current` completed successfully and returned:

```text
9647971e5956 (head)
Context impl PostgresqlImpl.
```

Directly querying the configured PostgreSQL database returned:

| Table | Actual row count |
| --- | ---: |
| `users` | 9 |
| `students` | 5 |
| `class_sessions` | 0 |
| `attendance_records` | 0 |
| `student_cases` | 0 |

Related live counts: `timetable_entries=1`, `guardians=1`, and `schedule_overrides`, `course_plans`, `makeup_suggestions`, `notifications`, `audit_logs`, `import_jobs`, `case_interactions`, and `attendance_changes` are all `0`.

The running backend responded to `GET /health` with:

```json
{"status":"healthy","service":"AntimBench API"}
```

**Conclusion:** the database is connected and migrated to the Alembic head. It contains real identity/academic seed data and one timetable entry, but it is **not populated with operational attendance, case, notification, reporting, audit, override, import, or course-plan data**. The result is proven by the row counts above.

## 2. User accounts — actual live rows and login checks

The following are every `users` row in the configured database. Passwords are deliberately not reproduced in this report. “Verified” means the audit made a real login request and then successfully called `/api/v1/auth/me`; it does not merely mean that a database row exists.

| Email | Database role | Active | Login result |
| --- | --- | --- | --- |
| `admin@antimbench.example.com` | admin | yes | **Verified:** login and `/auth/me` succeeded. Frontend target `/admin/dashboard` exists. |
| `teacher@antimbench.example.com` | teacher | yes | **Verified:** login and `/auth/me` succeeded. Frontend target `/teacher/sessions` exists. |
| `substitute@antimbench.example.com` | teacher | yes | **Verified:** login and `/auth/me` succeeded. This is a teacher-role account, not a distinct substitute role. |
| `student1@antimbench.example.com` | student | yes | **Verified:** login and `/auth/me` succeeded. Frontend target `/student/dashboard` exists. |
| `student2@antimbench.example.com` | student | yes | **Verified:** login and `/auth/me` succeeded. |
| `student3@antimbench.example.com` | student | yes | **Verified:** login and `/auth/me` succeeded. |
| `student4@antimbench.example.com` | student | yes | **Verified:** login and `/auth/me` succeeded. |
| `parent@antimbench.example.com` | parent | yes | **Verified API login:** login and `/auth/me` succeeded. **Frontend redirect is broken:** login sends it to `/parent/dashboard`, which is not a route; the implemented page is `/parent/notifications`. |
| `juniorjkberlin@gmail.com` | student | yes | **Not verified:** this appears to be a manually created/self-signup account; no supplied or seed credential exists to test it without guessing a password. |

Role coverage now:

| Requested role | Working account now? | Audit result |
| --- | --- | --- |
| Student | Yes | Four seed students have verified logins; one additional student row is unverified. |
| Teacher | Yes | Teacher and substitute-teacher accounts both verified. |
| Admin | Yes | Admin login verified. |
| Coordinator | **No** | No coordinator row exists, so the coordinator workflow cannot be logged into live. |
| Parent | Yes, API only | Parent API login works; UI redirect points to a missing route. |
| Super admin | **No** | `SUPER_ADMIN` is absent from the backend enum and frontend role type, and no account exists. |

The frontend’s redirect rule is teacher → `/teacher/sessions`, student → `/student/dashboard`, and every other role → `/${role}/dashboard`. This makes admin correct, but parent and any future coordinator incorrect because those dashboard routes do not exist.

## 3. Feature-by-feature status

| Feature | Status | Evidence and precise limitation |
| --- | --- | --- |
| User login (per role) | **PARTIALLY WORKING** | Live API logins verified for student, teacher, admin, and parent. No coordinator/super-admin account; parent redirect is broken. |
| User signup | **PARTIALLY WORKING** | Student-only API and form exist; signup integration test passes in an isolated test database. Not run against live DB because an audit should not add a user. No staff signup or invite/reset workflow. |
| Teacher views current scheduled session | **PARTIALLY WORKING** | Live teacher API returned the seeded Software Architecture session. UI route exists, but no authenticated browser was available to click it. |
| Teacher starts session and generates QR | **PARTIALLY WORKING** | Start and signed, expiring QR endpoints exist and are covered by integration tests. No live session was started during this non-mutating audit. |
| Student QR check-in | **PARTIALLY WORKING** | API/test flow exists. The frontend provides a QR display and manual token paste; `QRScanner` itself is only a placeholder, so there is no actual camera scanner. |
| Geofence validation | **PARTIALLY WORKING** | Server checks GPS accuracy and Haversine distance against configured thresholds; tests cover it. It was not exercised with a physical device/location in this audit. |
| Teacher live attendance roster | **PARTIALLY WORKING** | Roster endpoint and four-second polling UI exist. Live DB has no session/attendance record, so a live roster update was not demonstrated. |
| Manual attendance correction with reason | **PARTIALLY WORKING** | Endpoint requires a nonblank reason, creates an attendance-change row and audit entry; test passes. No live record exists to correct. |
| Session finalization / mark absent | **PARTIALLY WORKING** | Endpoint inserts absent/leave records for missing students and completes the session; test passes. No live session was finalized. |
| Admin schedule override | **PARTIALLY WORKING** | Create/list/approve/reject endpoints and UI exist; no live override exists. |
| Substitute access to override | **PARTIALLY WORKING** | Effective teacher logic blocks the original teacher and allows the substitute; isolated integration coverage exists. No actual override exists to prove it live. |
| Bulk CSV student import | **PARTIALLY WORKING** | Admin upload, row-level error handling, and import history exist; test passes. No live import was made. Imported accounts use one fixed temporary password. |
| Course completion tracking | **PARTIALLY WORKING** | Plans and completion increment on finalization exist; no `course_plans` row exists live. |
| Makeup suggestion generation | **PARTIALLY WORKING** | Conflict-search code and endpoint exist; no course plan/data was available for a live result. |
| Makeup approval becomes override | **PARTIALLY WORKING** | Approval creates an approved schedule override and queues notifications; tested in isolation, not live. |
| Risk evaluation | **PARTIALLY WORKING** | Correct threshold/minimum-observation implementation and tests exist, but evaluation is an **admin-triggered POST**, not automatic. Live has zero completed observations. |
| Automatic CRM case creation | **PARTIALLY WORKING** | A case is created when an admin manually runs risk evaluation; it is not event/worker-driven automatically after finalization. |
| Case deduplication | **PARTIALLY WORKING** | The phase-4 test runs evaluation twice and verifies one active case; PostgreSQL has partial unique index `uq_active_case`. Live conditions cannot trigger it because there are no records. |
| Case assignment, interactions, statuses, closing | **PARTIALLY WORKING** | Backend/UI exist; status change audit exists and closing requires a note. Assigning requires an `admin` or nonexistent coordinator login; no live case exists. Interaction creation itself has no audit entry. |
| CSV export | **PARTIALLY WORKING** | Attendance, cases, and course-completion CSV endpoints exist; report tests pass. Live exports would be empty because relevant tables are empty. |
| PDF export | **PARTIALLY WORKING** | Attendance and case PDF endpoints exist; tests verify PDF bytes. Rendering silently falls back from WeasyPrint to ReportLab, so visual output is environment-dependent. |
| Notification creation / guardian alerts | **PARTIALLY WORKING** | Notification rows are queued when a new risk case is created and for approved makeup classes; no live notifications exist. SMTP fields are blank and no delivery/sending worker is implemented. |
| Audit log for every mutation | **PARTIALLY WORKING** | Viewer and entries exist for attendance correction, override decision, import completion, case assignment/status, and approved makeup. Missing for signup, academic creates, timetable create, override create, session start, QR issuance, check-in, finalization, plan create, makeup suggestion creation/rejection, and case interactions. |
| Parent/guardian notification view | **PARTIALLY WORKING** | Parent-scoped endpoint and `/parent/notifications` page exist. Parent has one linked student but zero live notifications; post-login redirect is wrong. |
| Admin dashboard | **PARTIALLY WORKING** | Uses live API, not mock values. Current result is 0% attendance, 0 cases, 0 pending overrides, 0 pending suggestions because database data is empty. |
| Student dashboard | **PARTIALLY WORKING** | Uses live `/auth/me` plus attendance-summary API, not static/mock data. Live result for student1 is 0.0% and no subjects because there are no completed records. |

## 4. Dashboard-by-dashboard status

All listed Next.js routes returned HTTP 200 from the running frontend. A controllable browser was unavailable in this environment, so actual visual clicks/authenticated navigation could not be performed; route/data checks and source inspection were used instead.

| Dashboard | What is real now | What is missing or placeholder |
| --- | --- | --- |
| Student dashboard | Real API calls. Live request returned `student_id: 1`, `overall_percentage: 0.0`, `subjects: []`; it is not mock data. | Empty due to no attendance. Browser rendering/chart interaction not directly verified. |
| Teacher dashboard/session | `/teacher/sessions` gets real current-session/history APIs. The live API returned one current scheduled session and no history. Session-detail page has real QR SVG, polling roster, finalize, and correction calls. | No live class session/QR/roster exists. `QRScanner` component is a literal placeholder, while the student workflow only supports pasted token. |
| Admin dashboard | Calls live college-summary and at-risk APIs. Current response is 0% / zero counts, matching the actual empty operational tables. | It does not display a general college student/session count; browser chart was not rendered in this audit. |
| Coordinator case queue | Real `/cases` API and detail UI exist. | No coordinator account and no cases make it inaccessible/unproven live. Login would redirect a coordinator to missing `/coordinator/dashboard`, not `/coordinator/cases`. |
| Parent dashboard | A real notifications page calls the guardian-scoped API; the parent has one linked student and zero notifications. | There is no `/parent/dashboard`; successful parent login is redirected there and therefore fails to reach the real notifications view. |
| Super-admin view | **Not implemented.** | No schema role, account, route, layout, or dashboard exists. |

Additional frontend gaps: `/admin/timetable` and `/student/reports` are heading-only pages; they are placeholders. Role navigation is only a minimal header, and authorization is client-side JWT decoding from `localStorage` rather than server-side route protection.

## 5. Known gaps and deviations from a production system

- The live environment is PostgreSQL on local port **5432**, whereas the README’s Docker example describes port 5433. Tests also use isolated SQLite-style test setup for most behavior, so passing tests are not proof of a complete live PostgreSQL workflow.
- The live database is migrated and connected but operationally empty: zero sessions, attendance records, cases, notifications, audits, imports, overrides, plans, and suggestions.
- QR check-in has no device-camera scanner; the visible workflow uses pasted QR tokens. Geolocation has only test coverage here, not real mobile/browser validation.
- QR tokens and JWT authentication are good prototype mechanisms, but access JWTs are stored in browser `localStorage`, exposing them to XSS token theft. There is no HttpOnly-cookie/BFF design.
- Parent and coordinator frontend redirects are incorrect. There is no super-admin role or UI.
- Student self-signup is enabled. Teachers/staff cannot self-register, and there is no invitation/password-reset/account-recovery flow.
- CSV-imported students all receive the fixed temporary password `Welcome123!`; no forced reset or secure onboarding token exists.
- Risk evaluation is admin-triggered, not automatic. CRM case creation follows that manual action rather than session finalization/background events.
- Notifications are durable database rows only. SMTP configuration is blank, and there is no demonstrated email/SMS sending or delivery tracking. “Guardian alerts” should not be described as messages actually sent.
- PDF output tries WeasyPrint but silently falls back to ReportLab. PDFs exist, but layout/feature parity varies with the installed environment.
- Audit logging is selective, not comprehensive; numerous listed mutations write no audit record.
- Course completion, makeup, CRM, and exports have backend implementations and integration tests, but the live demo database has no data to demonstrate them.
- The frontend has route-level role checks based only on a decoded token in local storage and does not provide server-side protection. Some routes are functional but not polished: timetable/reports are placeholders and the teacher/student dashboard logic has not been interactively browser-tested in this audit.

## Verification summary

- Backend health: **passed**.
- Alembic current/head: **passed** (`9647971e5956`).
- Direct PostgreSQL reads: **passed**, exact counts recorded above.
- Live API login: **passed** for seeded student, teacher, substitute, admin, and parent accounts.
- Backend integration suite: **16 passed**, **1 dependency deprecation warning**.
- Live frontend route serving: **HTTP 200** for all audited routes.
- Authenticated browser navigation/visual interaction: **not performed** because no controllable browser was available in this audit environment.
