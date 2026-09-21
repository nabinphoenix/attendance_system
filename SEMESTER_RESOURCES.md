# Semester feedback and academic calendars

## Setup

From `backend/`, install the locked dependencies and apply the migration before starting the API:

```powershell
uv sync --locked
uv run --locked alembic upgrade head
```

Migration `j4e5f6g7h8i9` adds `teacher_feedback` and `academic_calendars`. Both tables inherit college ownership and database reference protections. Existing records are retained.

## Admin workflow

1. Open **Academic > Semester resources**.
2. Select the intake, batch, dated semester, and (where relevant) attempt. Use **Promotions** to create a cohort semester if it does not exist.
3. Upload the academic calendar PDF. The maximum file size is 10 MiB (10,485,760 bytes). Encrypted, empty, and unreadable PDFs are rejected. A replacement updates the same semester's calendar.
4. Assign teachers in the semester routine, then select a teacher in the feedback section.
5. Paste a published Google Forms **responder** link: `https://forms.gle/...` or `https://docs.google.com/forms/d/.../viewform`. Editor links are rejected.
6. Set the opening and closing dates and enable **Publish to students during this window**. A new form defaults to a two-week window starting at the semester midpoint, shortened if necessary to end within the semester.
7. Save. Each teacher has one feedback configuration per cohort semester; saving again updates it. Drafts are visible only to admins.

Feedback dates are inclusive and use `ACADEMIC_TIMEZONE` (default `Asia/Kathmandu`). Both dates must fall inside the semester.

## Student and teacher access

- Students open **Semester resources** to download their calendar and access published feedback for teachers assigned to their current section, including combined classes.
- Scheduled and closed forms show their dates without a responder link. Open forms launch in a new Google Forms tab.
- Students with dated enrollment history can still download calendars for their previous semesters. Ended and withdrawn placements do not grant current feedback access.
- Teachers open **Academic calendars** for the semesters in which they teach.
- College administrators manage resources only in their own college. Super admins must select a college workspace.

## Google Forms scope

This integration stores responder links. It does not create Google Forms, sign users into Google, synchronize responses, or infer successful submission from opening a link. Responses stay with the Google Form owner.

Configure responder access and **Limit to 1 response** in Google Forms when needed. The availability window in AntimBench controls the link shown in this app; configure response collection dates in Google Forms as well. See Google's [publishing and sharing guide](https://support.google.com/docs/answer/2839588).

## Storage and deployment

PDFs are stored as private binary data in PostgreSQL, so no public file directory or external storage credentials are required. Downloads require authentication and semester access. Audit records contain metadata, never the uploaded bytes.

The Elastic Beanstalk nginx API location allows 11 MiB request bodies to accommodate a 10 MiB PDF plus multipart overhead. Any additional gateway should allow the same request size.

## API

All paths below start with `/api/v1/academic/semester-resources`.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/semesters` | Admin, student, teacher; filtered by access |
| GET | `/semesters/{id}/teachers` | Admin |
| GET | `/semesters/{id}/feedback` | Admin or eligible student |
| PUT | `/semesters/{id}/feedback/{teacher_id}` | Admin; create or replace configuration |
| DELETE | `/semesters/{id}/feedback/{teacher_id}` | Admin |
| PUT | `/semesters/{id}/calendar` | Admin; multipart field `file` |
| GET | `/semesters/{id}/calendar` | Admin or eligible student/teacher |
| DELETE | `/semesters/{id}/calendar` | Admin |

Run the feature regression tests with `uv run --locked pytest tests/test_semester_resources.py -q`.
