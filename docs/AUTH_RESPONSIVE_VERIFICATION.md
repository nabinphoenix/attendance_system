# Authentication and responsive implementation

Status: implemented and verified locally. Verification completed 24 September 2026 (Asia/Katmandu). No production deployment or external email delivery was performed.

## Authentication

All interactive roles (Student, Teacher, Coordinator, Admin, Super Admin, and Parent) share the same protection. Each wrong password increments the persisted counter; attempts 1-4 return a generic 401, attempt 5 locks the account and returns 423. Counters stop at the configured threshold. A correct password cannot authenticate a locked account. Successful authentication before lockout clears the failure count and timestamps. PostgreSQL row locks serialize competing attempts.

User fields added by migration `p4q5r6s7t8u9_authentication_security.py` (after `o3p4q5r6s7t8`):

| Field | Purpose |
| --- | --- |
| `failed_login_attempts` | Consecutive wrong passwords; default 0 |
| `is_locked` | Lock flag; default false |
| `locked_at`, `last_failed_login_at` | UTC security timestamps |
| `session_version` | Default 0; JWT `sv` claim checked on authenticated requests |
| `reset_token_hash` | Unique nullable SHA-256 digest, never the raw token |
| `reset_expires_at`, `reset_requested_at` | Expiry and email cooldown |

The migration also creates `auth_rate_limits` (`key`, `count`, `expires_at`). Existing accounts receive safe defaults. Upgrade, downgrade and re-upgrade were verified in the isolated local PostgreSQL test database.

### Recovery and unlock

- Login offers **Forgot password?** and specific locked-account recovery/contact-admin guidance. Invalid credentials remain generic; rate-limit responses are readable.
- `POST /api/v1/auth/forgot-password` accepts an email and returns the same generic message for known, unknown, inactive, cooldown, and per-email-throttled accounts. IP throttling returns 429 without account details.
- Recovery generates 32 random bytes through `secrets.token_urlsafe(32)`, stores only their SHA-256 digest, and expires after 15 minutes by default. New challenges supersede old ones.
- Email uses the existing SMTP settings, transport and email template. Delivery runs after the HTTP response. The token lives only in memory and the email, not the notification database. Delivery errors omit exception details and secrets.
- Links use `/reset-password#token=...`; the fragment avoids normal HTTP URL/referrer logs. The page captures it, removes it from the address bar, and submits it in the POST body.
- `POST /api/v1/auth/reset-password/validate` checks an active, unexpired challenge. `POST /api/v1/auth/reset-password` checks matching new/confirmation passwords and consumes it atomically.
- Passwords use existing bcrypt hashing. Reset validation requires at least 8 characters, rejects a small set of common/repeated passwords, and enforces bcrypt's 72-byte bound. No arbitrary composition requirements were added.
- Reset updates the password hash, clears failure/lock state, consumes the challenge, increments `session_version`, clears the current session cookie and requires sign-in. Old cookie and bearer JWTs are rejected. Locking also revokes existing sessions; authenticated password changes rotate the current cookie while revoking earlier tokens.
- `POST /api/v1/users/{id}/unlock` is scoped to an Admin's college and excludes platform accounts. `POST /api/v1/platform/users/{id}/unlock` requires Super Admin. User-management tables show Locked, failure count and **Unlock account**, with an accessible confirmation dialog. Unlock clears lock/failure state and pending recovery, audits the acting administrator and leaves the password unchanged.

### Throttles and audit

All limits are configurable in `backend/app/core/config.py` and documented in `backend/.env.example`. Defaults:

| Control | Default |
| --- | --- |
| Consecutive failure threshold | 5 |
| Login requests per IP | 60 / 5 minutes |
| Reset requests per IP | 10 / 15 minutes |
| Reset requests per email | 3 / 15 minutes |
| Reset email cooldown | 60 seconds |
| Combined reset validation/completion requests per IP | 20 / 15 minutes |
| Challenge lifetime | 15 minutes |

Rate limits use atomic database upserts across workers/restarts, bounded counts, expiration cleanup and HMAC-hashed bucket identifiers. Client-IP handling reuses the existing trusted-proxy logic. Audit events include `auth.login_failed`, `auth.account_locked`, `auth.password_reset_requested`, `auth.password_reset_completed`, and `auth.account_unlocked`, with target/actor information. Passwords, hashes, OTPs and reset tokens are excluded from these events.

## Responsive changes

The existing AntimBench colors, typography, radii and light/dark styles remain. Base styles target phones; `sm` introduces two-column filters/forms, `lg` restores the desktop sidebar, and `xl`/`2xl` add wider grids when space permits. No fixed device-width layout or global horizontal-overflow hiding was added.

Shared changes:

- `RoleShell`: shrinkable full-width content, compact header, no mobile sidebar offset; a native modal drawer with keyboard focus containment, Escape/overlay dismissal, focus restoration, independent expanded mobile navigation, and close-on-navigation. College-context Super Admins have **Back to platform** inside the drawer.
- `Card`, `PageHeader`, `Button`, `Brand`, global form styles: width constraints, sensible phone padding/type, wrapping actions, and approximately 44px phone controls. Sixteen-pixel phone form text avoids iOS focus zoom.
- `ScheduleFilterBar`: one phone column, two tablet columns, three on wide screens; search spans the available row. Selects and inputs occupy their cells without forced desktop minimum widths. Clear remains accessible.
- Student Dashboard: full heading and Check in action stay within the page; filters/search and Today's classes fit the viewport. Shared schedule cards wrap course, time, lecturer, room and status naturally.
- Settings: photo title, centered avatar, readable description, full-width Upload photo action and file guidance stack on phones; desktop can use horizontal composition. Profile/security fields and actions fit narrow cards; long email text wraps.
- `ConfirmDialog`: native modal semantics, labelled controls, focus trapping/restoration, constrained width/height, vertical scrolling, stacked narrow actions and recoverable request errors. `AuthCard.Field` associates labels and help/error text with their controls and disables server-rendered inputs until React is ready, preventing early typing from being lost during hydration.
- Tables: internal horizontal scroll regions with width constraints and keyboard access. The page stays within its viewport, and table text wraps at word boundaries instead of splitting short headings into fragments. Containment also prevents absolutely positioned screen-reader headings escaping the page.
- Teacher live session: QR/code/details stack until there is room; readable roster cards show student/status/GPS/network evidence and wrap into a wider grid only at larger breakpoints. Student self-check-in remains QR or attendance code; no gallery upload was introduced.
- Academic batch/promotion forms use responsive columns, and preview/held-student tables stay contained. Promotion/placement controls received explicit accessible labels.

Pages receiving shared or direct improvements include Student dashboard/routine/reports/check-in, Teacher timetable/live sessions/attendance/analysis, Admin dashboard/user access/academic setup/batches/modules/module offerings/promotions/semester resources/routine/imports/analytics/audits/course completion, Coordinator cases, Super Admin user access/audits, Settings, Login, Forgot password and Reset password. Shared room availability, routine, invitation and import panels also use contained tables.

## Verification

| Check | Result |
| --- | --- |
| Full backend suite | **167 passed, 1 skipped** (978.60 s) |
| Authentication tests on PostgreSQL | **18 passed** (90.99 s), including concurrent fifth-attempt lockout and single-use reset races |
| Additional SMTP delivery/secrecy test | **1 passed** (1.37 s); added after full-suite collection |
| Migration upgrade/downgrade/re-upgrade | **Passed**, isolated localhost `attendance_test` |
| Frontend production build | **Passed**, TypeScript and 53 static pages generated |
| Frontend lint | **0 errors, 9 existing warnings** |
| Responsive/E2E | **66 passed** (7.3 minutes): 22 per browser, including 960 page/viewport/theme checks |
| Source whitespace/error-marker review | `git diff --check` clean; only Git's line-ending normalization notice |

The skipped backend case is the PostgreSQL-only concurrency test in the normal SQLite fixture run; it passed in the dedicated PostgreSQL run. A pre-existing scheduling test fixture was corrected to span the full test day, avoiding expiration during setup after 23:00. Application scheduling logic was unchanged.

Browser automation uses populated mock API responses with long names and course titles; real backend security and business-rule tests are separate. Desktop Chrome, Android Chrome device emulation (Pixel 7), and iPhone WebKit emulation are exercised. Tool versions: Playwright 1.63.0, installed Chrome 154.0.8037.57, and WebKit 26.6 (revision 2359). These are not physical-device tests. Camera hardware, real location acquisition and external email delivery were not end-to-end tested; existing attendance/GPS/network backend tests cover their rules.

Each browser runs both themes at 320x568, 360x800, 375x812, 390x844, 412x915, 430x932, 768x1024 and 1440x1000. Twenty representative routes assert that document width equals viewport width, rendered content stays inside the page except intentional table scroll regions, theme selection is correct, and no page JavaScript errors occur. Interaction cases cover drawer keyboard behavior/navigation, filter changes/clear, locked login/recovery/password confirmation, confirmed admin unlock, QR/code-only controls/live roster, and shuffle preview/held-student decisions.

The workspace drive ran out of space during initial verification. Generated `.next` output was removed, and the same frontend source was built/tested in a temporary directory on C: (file hashes were compared with the workspace after testing started) to avoid consuming the workspace drive. No source or deployment artifacts were deleted. Test reports and screenshots were produced by Playwright.

### Screenshots

Full-page screenshots of populated test workspaces from the final Chrome run. The mobile dashboard, profile photo composition, teacher roster and desktop layout were also visually inspected.

| Page | Phone (390px) | Desktop (1440px) |
| --- | --- | --- |
| Student dashboard | [Light](screenshots/auth-responsive/student-dashboard-390-light.png) / [Dark](screenshots/auth-responsive/student-dashboard-390-dark.png) | [Light](screenshots/auth-responsive/student-dashboard-1440-light.png) / [Dark](screenshots/auth-responsive/student-dashboard-1440-dark.png) |
| Settings / profile photo | [Light](screenshots/auth-responsive/settings-390-light.png) / [Dark](screenshots/auth-responsive/settings-390-dark.png) | [Light](screenshots/auth-responsive/settings-1440-light.png) / [Dark](screenshots/auth-responsive/settings-1440-dark.png) |
| Teacher live session | [Light](screenshots/auth-responsive/teacher-sessions-1-390-light.png) / [Dark](screenshots/auth-responsive/teacher-sessions-1-390-dark.png) | [Light](screenshots/auth-responsive/teacher-sessions-1-1440-light.png) / [Dark](screenshots/auth-responsive/teacher-sessions-1-1440-dark.png) |

### Repeat the checks

- Backend regression suite: from `backend`, set `DATABASE_URL` to a disposable migrated local test database and run `.venv\Scripts\python.exe -m pytest -q`. Do not point tests at production.
- Authentication races: set `ATTENDANCE_TEST_POSTGRES_URL` to the local test database and run `.venv\Scripts\python.exe -m pytest tests/test_auth_security.py -q`; the fixtures create isolated schemas.
- Frontend: from `frontend`, run `npm run build`, `npm run lint`, and `npm run test:e2e`. Install Playwright browsers first with `npx playwright install chromium webkit`. Set `PLAYWRIGHT_CHROME_CHANNEL=chrome` to use installed Chrome for the Chromium projects, as in this verification.
- Playwright starts the local built application on port 3100 and writes its HTML report to `frontend/playwright-report`. UI fixtures intercept the API requests; they do not modify an external account or college.

## Local startup and remaining warnings

The existing localhost `antimbench` development database is now at `p4q5r6s7t8u9`. Only the new additive authentication revision was applied after verifying the expected prior revision; the existing account count and default unlocked state were checked afterward. The revision was first verified against a separate localhost `attendance_test` database. For another local checkout/database, run `python -m alembic upgrade head` from `backend` with its intended environment. Production was not migrated. Configure the existing SMTP settings and a correct `FRONTEND_URL` for working reset links. No AWS credentials were read or changed.

- Frontend lint has nine pre-existing `react-hooks/exhaustive-deps` warnings: Admin assistant/routine, Coordinator cases/detail, AcademicSetupPage, OverrideWorkspace (two), RoutineMasterPage and TeacherTimetablePanel.
- `npm audit` reports three pre-existing dependency advisories: Next 16.3.2 (critical), sharp 0.35.3 (high), and js-yaml 4.3.1 (high). The lockfile had those same versions before this change. They were not introduced by Playwright and remain unresolved; dependency patching should be handled before production release.
- The existing standalone Next configuration emits a warning when the Playwright local server uses `next start`; the server serves the built app and the tests verify it. The temporary C: build also warns that an unrelated home-directory lockfile was ignored. Browser tooling emits a harmless FORCE_COLOR/NO_COLOR warning.
- Physical Android/iPhone verification and real SMTP delivery remain environment-dependent follow-up checks. Automated mobile emulation and fake-SMTP delivery verification do not claim those hardware/infrastructure checks.
