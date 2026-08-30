# Simple guide: set up data and import in bulk

This guide is for an **Admin**. It explains how to set up a new intake or new
semester, add teachers, import students, import a routine, and send student
emails.

Please do the setup in the order below. A CSV or Excel import file cannot
create programmes, modules, teachers, rooms, or time slots by itself. Those
items must be created in AntimBench first.

## Simple order to follow

```text
Programme
   ├─ Batch
   └─ Intake
        └─ Section (Batch + Intake + Semester)

Module + Intake + Batch + Semester = Module offering
```

For every new intake or semester, do these steps in order:

1. Create the programme.
2. Create the batch.
3. Create the intake.
4. Create the sections.
5. Create the modules.
6. Create module offerings.
7. Create class types, blocks, rooms, and time slots.
8. Create teacher accounts.
9. Import the routine.
10. Import students.
11. Send student activation emails when needed.

> An **intake** and a **batch** are different things. Create both under the
> same programme. A section joins them together. For example: batch `2026`,
> intake `SEP-2026`, semester `1`, section `A1`.

## Step 1: Create the basic academic data

Open **Admin → Academic**. Create these items before you import students or a
routine.

| What to create | What to enter | Why it is needed |
| --- | --- | --- |
| Programme | Programme name | The main course, for example BSc Computing. |
| Batch | Batch name and programme | The group of students, for example `2026`. |
| Intake | Name, unique code, start date, programme | The routine file uses the intake **code**, for example `SEP-2026`. Use the same programme as the batch. |
| Section | Section name, batch, intake, semester | Create every group such as `A1`, `A2`, `A3`, and `A4`. Always choose the correct intake and semester. |
| Module | Module code, module name, credits, semester number | The code and semester must be the same as the routine file. |
| Module offering | Module, intake, batch, semester, active status | This says that the module is taught to this batch in this intake and semester. Make one active offering for each module. |
| Class type | Names such as `Lecture`, `Tutorial`, `Practical` | The routine file can only use class types that already exist. |
| Block and room | Block name, then room name inside that block | The block and room in the routine file must already exist. |
| Time slot | Start time and end time | The times in the routine file must match a saved time slot exactly. |

### Example for a new intake

For a new September 2026 intake, you may create:

```text
Programme: BSc (Hons) Computing
Batch: 2026
Intake code: SEP-2026
Sections: A1, A2, A3, A4
Semester: 1
Modules: all Semester 1 modules
Module offerings: one active offering for every Semester 1 module
```

Do not upload a routine until all of these items are ready.

## Step 2: Create teacher accounts

Open **Admin → Academic → Teachers**. Add teachers one by one.

| Field | Needed? | Notes |
| --- | --- | --- |
| Name | Yes | Teacher's full name |
| Email | Yes | Must be unique. Use this same email in the routine file. |
| Password | Yes | The teacher uses this to sign in. |
| Employee code | Yes | Must be unique. |

At the moment, AntimBench does **not** have a CSV/Excel bulk import for teacher
accounts. Create the teacher account first. Then assign the teacher in the
routine by using the same email address.

## Step 3: Prepare the student bulk-import file

Open **Admin → Imports**, choose **Students**, and download the template. You
can also find it here:
[student_import_template.csv](import_templates/student_import_template.csv).

### File rules

- You can upload a `.csv` or `.xlsx` file.
- If you upload Excel (`.xlsx`), it must have only one sheet and the sheet name
  must be **`Timetable`**. This is a current app rule, even for student files.
- Write the column names exactly as shown below. Do not rename them.
- The app does not understand new or custom column names.
- Extra columns are ignored. They are not saved.

### Student file columns

| Column name | Needed? | Simple meaning |
| --- | --- | --- |
| `name` | Yes | Student's full name. |
| `email` | Yes | Student's email. It must not already be used by another user or student. |
| `batch_name` | Yes | An existing batch name, for example `2026`. |
| `section_name` | Yes | An existing section name in that batch, for example `A1`. |
| `phone` | No | If added, the app makes a guardian contact with this phone number. It does not make a guardian login. |
| `roll_number` | No | Student roll number. If empty, the app creates one automatically. |

Example student file:

```csv
name,email,batch_name,section_name,phone,roll_number
Aarav Sharma,aarav.sharmasep26@cps.edu.np,2026,A1,9800000000,SEP26-001
Sita Rai,sita.raisep26@cps.edu.np,2026,A1,9800000001,SEP26-002
```

### Import students

1. Check that the batch and section already exist.
2. Check that the section is connected to the correct intake and semester.
3. Open **Admin → Imports** and choose **Students**.
4. Upload the completed file and start the import.
5. Read the import result.
6. Fix only the rows that failed, then upload only those rows again.

The student import does not update old students. If an email already exists,
that row fails. Do not upload students who were already imported successfully.

> Use a clear batch name and section name. For example, do not use the same
> batch/section names for different groups if you can avoid it. The student
> importer uses the batch name and section name; it does not use an intake code
> in the student CSV.

## Step 4: Check everything before routine import

Before importing a routine, make sure:

- The intake code exists.
- The sections exist for the correct batch, intake, and semester.
- The module exists and is set to the same semester as the routine row.
- There is an **active module offering** for that module, intake, batch, and
  semester.
- The class type, block, room, and time slot already exist.
- The teacher account already exists.
- The teacher email in the file is exactly the same as the teacher account
  email.

Write time as `HH:MM` or `HH:MM:SS`, for example `08:30` or `08:30:00`. The
start time and end time must exactly match one saved time slot.

You can write days as `MON` to `SUN`, or full names such as `Monday`.

## Step 5: Import a routine for one section (best option)

Open **Admin → Routine → Import a section routine**.

1. Choose the intake, semester, and section.
2. Download the template from that page.
3. Fill in the file.
4. Upload the file and click **Preview**.
5. Fix all errors shown in Preview.
6. When there are no invalid rows, click **Import**.

Use these column names exactly:

```csv
day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room
```

Example:

```csv
day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room
SUN,08:30,09:30,A1,CT004-3-3,Advanced Database Systems,Lecture,teacher@cps.edu.np,Block B,Machapuchare-L04
MON,09:30,11:00,A1|A2,CT004-3-3,Advanced Database Systems,Practical,teacher@cps.edu.np,Block B,Machapuchare-L04
```

Important rules:

- The `sections` value must contain the section you selected on the page.
- For one class with two or more sections, use `|`, for example `A1|A2`.
  Do not use a comma inside that cell.
- Write the correct module title in `module_title`.
- `lecturer_email` must be the email of a teacher account that already exists.
- Create all sections and module offerings before importing a combined class.
- Preview must show no invalid rows before you can import.

## Step 6: Import a routine for one teacher

You can also import a teacher's timetable from the teacher timetable page.

1. Select the teacher first.
2. Download the teacher timetable template.
3. Upload the completed file and preview it.
4. Fix errors, then import.

The teacher is selected on the page, so this file does not need a teacher email
column.

```csv
intake_code,semester,sections,day,start_time,end_time,module_code,class_type,block,room
NPT3F2509IT,SEM VI,A3|A4,SUN,08:30,09:30,CT004-3-3,Lecture,Block B,Machapuchare-L04
```

For `semester`, you can write `6`, `SEM VI`, or `Semester 6`.

## Step 7: Import many routine rows from one file

Open **Admin → Imports**, choose **Routines**, and download the template:
[routine_import_template.csv](import_templates/routine_import_template.csv).

The normal template columns are:

```csv
intake_code,semester_number,section_name,module_code,class_type,teacher_email,block_name,room_name,day_of_week,start_time,end_time
```

The app also accepts these other names. These are the only supported changes;
you cannot make your own column names.

| What it means | You can use either column name |
| --- | --- |
| Semester | `semester_number` or `semester` |
| Section or sections | `section_name` or `sections` |
| Teacher email | `teacher_email` or `lecturer_email` |
| Block | `block_name` or `block` |
| Room | `room_name` or `room` |
| Day | `day_of_week` or `day` |

For a class with more than one section, use the `sections` column and write
the section names with `|`, for example `A1|A2`.

The app saves valid rows and shows errors for invalid rows. Read the error list,
fix the bad rows, and import only those rows again.

### Common routine problems

| Problem | What to do |
| --- | --- |
| Intake, module, class type, teacher, block, or room not found | Create it first, then check the spelling, code, name, or email in the file. |
| Module semester is wrong | The module semester and file semester must be the same. |
| Module offering not found | Create an active offering for that module, intake, batch, and semester. |
| Section not found | Check the section's batch, intake, and semester. |
| Time slot not found | Create a time slot with the exact same start and end time. |
| Class clash | Change a time that overlaps the same teacher, section, or room. |
| Day or time is wrong | Use an allowed day and `HH:MM` or `HH:MM:SS` time. |

## Step 8: Student accounts and email invitations

There are two different ways student accounts can exist in the app.

### Students imported from the student CSV

The current student bulk import makes a user account for every student that is
imported successfully. The starting password is currently `Welcome123!`.

The bulk student import does **not** send an activation email automatically.
For a real college system, it is safer to change this later to an
email-invitation or password-reset system before sharing accounts with students.
Do not post the starting password on a public website.

### Send an activation email to one or more students

Open **Admin → Students** and use the **Student onboarding** area.

1. Filter by intake or section if needed.
2. You can choose to show only students who do not have accounts.
3. Select one student to send one email, select many students, or invite all
   students shown in the filtered list.
4. Send the invitation.

The email has a link. The student opens the link, creates a password, and then
can sign in. The link normally expires after seven days.

> Important current limit: the email invitation screen sends emails only to
> students who do **not** already have an account. Because the student CSV
> import creates accounts, students imported from that file cannot receive these
> activation emails through that screen. If you need activation emails for a
> new intake, ask for an invitation-based bulk import before you import the
> students.

### Make sure email sending works

For emails to arrive, the backend must have these settings:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `FRONTEND_URL`

`FRONTEND_URL` must be the website students open, for example:
`https://antimbench-https-proxy.vercel.app`.

The background email worker must also be running:

```text
uv run python -m app.workers.worker
```

First send one test email. Check that it arrives and that its link opens the
correct public website.

Never put SMTP passwords, AWS keys, or other secret values in a CSV file, this
guide, or GitHub. Save them as deployment secrets.

## Checklist before you upload

- [ ] Programme exists.
- [ ] Batch and intake are under the same programme.
- [ ] Sections have the correct batch, intake, and semester.
- [ ] Modules have the correct code, name, and semester.
- [ ] Every module has an active module offering.
- [ ] Class types, blocks, rooms, and time slots exist.
- [ ] Teacher accounts exist and their emails match the routine file.
- [ ] File headers are exactly like the template headers.
- [ ] Excel files have one sheet named `Timetable`.
- [ ] Routine Preview has no errors.
- [ ] Student emails are unique.
- [ ] Email settings and email worker are ready if you want to send invitations.

## Good habits

- Download a fresh template before making a new file.
- Test with one or two rows first.
- Keep a copy of every CSV/Excel file and its import result.
- Fix and upload only failed rows.
- Finish the basic setup first. Import the routine only after the programme,
  batch, intake, sections, modules, rooms, teachers, and time slots are ready.
