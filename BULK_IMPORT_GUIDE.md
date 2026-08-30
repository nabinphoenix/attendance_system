# Bulk academic setup, imports, and student onboarding

This guide is for an **administrator** setting up a new intake/semester in
AntimBench. Follow the order in this document before importing students or a
routine. Imports validate references against the data already in the database;
they do not create programmes, modules, teachers, rooms, or time slots for you.

## The setup order at a glance

```text
Programme
 ├─ Batch (the student cohort)
 └─ Intake (the admission period)
      └─ Section = Batch + Intake + Semester

Module + Intake + Batch + Semester = Module offering
Module offering automatically includes the matching sections.
```

For each new intake/semester, use this order:

1. Create the programme.
2. Create the batch for the cohort.
3. Create the intake under the same programme.
4. Create the sections for that batch, intake, and semester.
5. Create the module catalogue entries.
6. Create an active module offering for every module taught in that intake,
   batch, and semester.
7. Create class types, blocks, rooms, and time slots.
8. Create each teacher account.
9. Import the routine and fix every invalid row.
10. Bulk-import students.
11. Send activation emails only to student profiles that do not already have
    an account. See [Student accounts and invitation emails](#student-accounts-and-invitation-emails).

> Important: an intake and a batch are separate records. Create both under the
> same programme. A section is where they meet: for example, `2026` batch +
> `JAN-2026` intake + semester `6` + section `A1`.

## 1. Create the academic master data

Use the **Admin → Academic** menu. Complete the following records before using
an import file.

| Create | Required information | Why it is needed |
| --- | --- | --- |
| Programme | Programme name | The parent record for a batch and an intake. |
| Batch | Batch name and programme | Students are imported into a batch and section. Use a cohort-specific name such as `2026` or `BSc CS 2026`. |
| Intake | Name, unique code, start date, programme | Routine files identify the intake by its **code**, for example `JAN-2026`. The intake programme must match the batch programme. |
| Section | Section name, batch, intake, semester | Create every teaching group, for example `A1`, `A2`, `A3`, and `A4`. Set the intake and semester; section-routine import checks both. |
| Module | Unique module code, title, credits, semester number | The code and semester must match the routine file, for example `CT004-3-3`, semester `6`. |
| Module offering | Module, intake, batch, semester, active status | This makes a catalogue module teachable to the cohort. It automatically uses sections belonging to the same intake, batch, and semester. Do **not** try to add sections manually to an offering. |
| Class type | Name such as `Lecture`, `Tutorial`, or `Practical` | Routine rows must use an existing class type. |
| Block and room | Block name; then room name within that block | Both names must already exist before routine import. A room is resolved inside its block. |
| Time slot | Start and end time | Every routine row must exactly match an existing time slot. |

### New-semester example

For a September 2026 semester, an administrator might create:

```text
Programme: BSc (Hons) Computing
Batch: 2026
Intake: SEP-2026 (under BSc (Hons) Computing)
Sections: A1, A2, A3, A4 (Batch 2026, Intake SEP-2026, Semester 1)
Modules: the Semester 1 module catalogue
Offerings: one active offering per module for SEP-2026 + Batch 2026 + Semester 1
```

Only after all of those records exist should the timetable or student file be
uploaded.

### Create teacher accounts

Go to **Admin → Academic → Teachers** and create every teacher individually.
The current application requires:

| Field | Requirement |
| --- | --- |
| Name | Required |
| Email | Required and unique; this exact address is used by routine imports |
| Password | Required initial password |
| Employee code | Required and unique |

There is currently **no CSV/XLSX bulk teacher-account importer**. A teacher is
assigned when a routine row uses that teacher's email, or when the teacher is
selected while creating a routine manually. Do not put a teacher email in a
routine file until that teacher account exists.

## 2. Prepare the student bulk-import file

Go to **Admin → Imports**, choose **Students**, and download the supplied
template. The repository copy is
[`import_templates/student_import_template.csv`](import_templates/student_import_template.csv).

### Supported format

- Upload a `.csv` or `.xlsx` file.
- An XLSX upload must contain exactly one worksheet named **`Timetable`**. This
  is a current application rule, including for student imports.
- Use the column names below exactly as written: lower-case, with underscores.
- The app does not dynamically map renamed headings. Extra columns are ignored;
  they are not saved.

### Student columns

| Column | Required | Notes |
| --- | --- | --- |
| `name` | Yes | Student's display name. |
| `email` | Yes | Must be unique across both users and student records. Use the student's college email. |
| `batch_name` | Yes | Must exactly identify an existing batch (matching is case-insensitive). |
| `section_name` | Yes | Must identify an existing section within that batch (matching is case-insensitive). |
| `phone` | No | When supplied, the system creates a guardian contact called `Guardian of <student name>` with this phone number. It does not create a guardian login. |
| `roll_number` | No | If blank, the system generates an import roll number such as `IMP-<job>-<row>`. |

Example:

```csv
name,email,batch_name,section_name,phone,roll_number
Aarav Sharma,aarav.sharmasep26@cps.edu.np,2026,A1,9800000000,SEP26-001
Sita Rai,sita.raisep26@cps.edu.np,2026,A1,9800000001,SEP26-002
```

### Import students

1. Confirm the batch and its sections already exist. For a new intake, make
   the section records point to the correct intake and semester before upload.
2. In **Admin → Imports**, select **Students** and upload the completed file.
3. Start the import and review the import job result.
4. Keep successful rows. Correct only the failed rows and upload those again.

The importer does not update an existing student. A duplicate email fails, so
do not re-upload students that have already imported successfully.

> Use an unambiguous batch/section combination. The current student importer
> selects by batch name and section name, not by an intake-code column. A
> cohort-specific batch name and sections correctly connected to the new intake
> avoid importing a student into the wrong similarly named section.

## 3. Import a routine

Before importing, verify all of the following:

- The intake code exists.
- The sections exist for the intended batch, intake, and semester.
- The module exists and its semester number matches the row.
- There is an **active module offering** for the module, intake, batch, and
  semester.
- The class type, block, room, and exact time slot exist.
- Every teacher email belongs to an existing teacher account.

Use `HH:MM` or `HH:MM:SS` for times, such as `08:30` or `08:30:00`. The start
and end pair must be exactly the same as a configured time slot. Supported day
values are `MON` through `SUN` or full English names such as `Monday`.

### Recommended: import one section routine with preview

Go to **Admin → Routine → Import a section routine**. Select the target intake,
semester, and section, download the fresh template from that screen, complete
it, then select **Preview** before selecting **Import**.

Use these template headings exactly:

```csv
day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room
```

Example:

```csv
day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room
SUN,08:30,09:30,A1,CT004-3-3,Advanced Database Systems,Lecture,teacher@cps.edu.np,Block B,Machapuchare-L04
MON,09:30,11:00,A1|A2,CT004-3-3,Advanced Database Systems,Practical,teacher@cps.edu.np,Block B,Machapuchare-L04
```

Rules for this file:

- `sections` must include the selected section. Use a vertical bar (`|`) for a
  combined class, for example `A1|A2`; do not use a comma inside the cell.
- `module_title` should be the exact catalogue title. If provided, it is checked
  against the module code.
- `lecturer_email` must be the email of a previously created teacher.
- The preview must have no invalid rows before the system permits the import.
- Create every combined section and its active module offering first. Otherwise
  an additional section can be recorded as a pending reference instead of a
  ready timetable entry.

### Alternative: import a teacher's timetable

In the teacher management/timetable area, select a teacher first, then download
the teacher timetable template, preview it, and import it. The teacher is
chosen in the screen, so the file does **not** contain a lecturer email.

```csv
intake_code,semester,sections,day,start_time,end_time,module_code,class_type,block,room
NPT3F2509IT,SEM VI,A3|A4,SUN,08:30,09:30,CT004-3-3,Lecture,Block B,Machapuchare-L04
```

`semester` accepts a number such as `6`, `SEM VI`, or `Semester 6`.

### Alternative: global routine import

Go to **Admin → Imports**, choose **Routines**, and use the repository template
[`import_templates/routine_import_template.csv`](import_templates/routine_import_template.csv).
This format is useful when one file contains entries for more than one section
or teacher.

The supplied headers are:

```csv
intake_code,semester_number,section_name,module_code,class_type,teacher_email,block_name,room_name,day_of_week,start_time,end_time
```

The global importer also accepts these documented aliases; it does **not**
support arbitrary or dynamic headers:

| Meaning | Accepted headings |
| --- | --- |
| Semester | `semester_number` or `semester` |
| Section(s) | `section_name` or `sections` |
| Teacher email | `teacher_email` or `lecturer_email` |
| Block | `block_name` or `block` |
| Room | `room_name` or `room` |
| Day | `day_of_week` or `day` |

For a combined class in this import, use `sections` and separate section names
with `|`, for example `A1|A2`.

The import job processes rows independently: valid rows are saved and invalid
rows are reported. Review its error list, repair the failing rows, and import
only those rows again.

### Common routine errors

| Error area | What to check |
| --- | --- |
| Unknown intake/module/type/teacher/block/room | Create the referenced master-data record first; then use its correct code, name, or email. |
| Module semester mismatch | The module's configured semester must equal the routine row's semester. |
| No active offering | Create an active offering for the exact module + intake + batch + semester. |
| Section is not available | Check the section's batch, intake, and semester. |
| Time slot not found | Create that exact start/end time-slot pair. |
| Clash | Change a row that overlaps the same teacher, section, or room. |
| Invalid day/time | Use an accepted day and `HH:MM`/`HH:MM:SS` time. |

## Student accounts and invitation emails

There are two different account states in the current application. It is
important not to mix them up.

### Accounts created by the student bulk importer

The current **Students** bulk importer creates a linked user account for every
successful row. Its initial password is currently the application default
`Welcome123!`. It does **not** automatically send an email invitation.

For a real production rollout, change this default-account workflow to a
password-reset or invitation-only flow before giving credentials to students.
Do not publish a shared initial password on a public page.

### Sending individual or bulk activation invitations

Go to **Admin → Students** and use the **Student onboarding** panel:

1. Filter the list by intake and/or section.
2. Optionally enable **only students without accounts**.
3. Select one student for an individual email, select multiple students, or use
   the option to invite all currently filtered eligible students.
4. Send the invitations and check the result shown by the panel.

An invitation contains an activation link. The student opens it, chooses a
password, and signs in. Links expire after the configured invitation lifetime
(the default is seven days).

**Current limitation:** the onboarding screen only invites student records that
do **not** have a linked user account. Because the existing bulk student
importer already creates an account, newly bulk-imported students will not be
eligible for these activation emails. If email activation is required for a new
cohort, use/create pre-account student profiles through the approved data setup
process and then send invitations, or request an invitation-based bulk-import
enhancement before importing them.

### Email delivery checklist

Sending an invitation creates a notification record, but email is delivered
only when the backend mail configuration and worker are available.

- Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and
  `SMTP_FROM_EMAIL` in the backend deployment environment.
- Set `FRONTEND_URL` to the public site students use. For the current Vercel
  deployment, this is normally `https://antimbench-https-proxy.vercel.app`.
- Run the notification worker with `uv run python -m app.workers.worker` (or
  ensure its production worker service is running).
- Send one test invitation first and verify that it arrives and that the link
  opens the public frontend.

Do not put SMTP passwords or cloud keys in this guide, in CSV files, or in the
Git repository. Store them as deployment secrets.

## Reusable new-intake checklist

Before uploading data for a new semester, confirm:

- [ ] Programme exists.
- [ ] Batch and intake exist under the same programme.
- [ ] Every section has the correct batch, intake, and semester.
- [ ] Modules have the correct unique code, title, and semester.
- [ ] Every taught module has an active offering for this intake, batch, and
      semester.
- [ ] Class types, blocks, rooms, and all time slots exist.
- [ ] Every teacher account exists and its email matches the routine file.
- [ ] CSV/XLSX headers match the downloaded template exactly.
- [ ] XLSX has one worksheet named `Timetable`.
- [ ] Routine preview has no invalid rows, or the import-job errors have been
      repaired.
- [ ] Student emails are unique and batch/section names resolve correctly.
- [ ] Mail settings and the notification worker have been tested if sending
      activation invitations.

## Practical import habits

- Always download the current template before starting a new file; do not
  rename its headers.
- Test a file with one or two rows before uploading an entire intake.
- Save a copy of the source CSV/XLSX and the import result for audit purposes.
- Correct and re-import only failed rows. Avoid re-uploading successful student
  rows because duplicate email addresses are rejected.
- Treat programme, batch, intake, sections, module offerings, rooms, and time
  slots as the foundation. Routine imports are the final scheduling step, not
  a replacement for academic setup.
