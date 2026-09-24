"use client";

import { FormEvent, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type Course = { id: number; code: string; title: string };
type Level = { id: number; intake_id: number; level_number: number; intake_code: string };
type Batch = { id: number; name: string; levels: Level[] };
type Semester = { id: number; batch_id: number; batch_level_id: number; intake_id: number; semester_number: number; display_name: string; attempt_number: number };
type Section = { id: number; batch_id: number; name: string };
type Assignment = {
  id: number; academic_module_id: number; module_code: string; module_title: string;
  intake_id: number; intake_code: string; batch_id: number; batch_name: string;
  semester_number: number; cohort_semester_id: number | null;
  section_ids: number[]; section_names: string[]; is_active: boolean;
};
type AssignmentData = { courses: Course[]; batches: Batch[]; semesters: Semester[]; sections: Section[] };
type AssignmentForm = { academic_module_id: string; batch_id: string; batch_level_id: string; cohort_semester_id: string; section_ids: number[]; is_active: boolean };

const blank: AssignmentForm = { academic_module_id: "", batch_id: "", batch_level_id: "", cohort_semester_id: "", section_ids: [], is_active: true };
const courseLabel = (course: Course) => `${course.code} — ${course.title}`;
const levelLabel = (level: Level) => `Level ${level.level_number} · ${level.intake_code}`;
const semesterLabel = (semester: Semester) => semester.display_name || `Semester ${semester.semester_number}`;

function errorMessage(error: unknown, fallback: string) {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
  return typeof detail === "string" ? detail
    .replace(/module offerings/gi, "course assignments")
    .replace(/module offering/gi, "course assignment")
    .replace(/cohort semester/gi, "semester")
    .replace(/\bmodule\b/gi, "course") : fallback;
}

export default function Page() {
  const [data, setData] = useState<AssignmentData>({ courses: [], batches: [], semesters: [], sections: [] });
  const [rows, setRows] = useState<Assignment[]>([]);
  const [form, setForm] = useState<AssignmentForm>(blank);
  const [edit, setEdit] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [pendingToggle, setPendingToggle] = useState<Assignment | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [courses, batches, sections, semesters, assignments] = await Promise.all([
        api.get<Course[]>("/api/v1/academic/modules"),
        api.get<Batch[]>("/api/v1/academic/batches"),
        api.get<Section[]>("/api/v1/academic/sections"),
        api.get<Semester[]>("/api/v1/academic/cohort-semesters"),
        api.get<Assignment[]>("/api/v1/academic/module-offerings"),
      ]);
      setData({ courses: courses.data, batches: batches.data, sections: sections.data, semesters: semesters.data });
      setRows(assignments.data);
      setError("");
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to load course assignments."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const selectedBatch = data.batches.find((batch) => batch.id === Number(form.batch_id));
  const levels = [...(selectedBatch?.levels ?? [])].sort((a, b) => a.level_number - b.level_number);
  const selectedLevel = levels.find((level) => level.id === Number(form.batch_level_id));
  const semesters = data.semesters.filter((semester) =>
    semester.batch_id === selectedBatch?.id && semester.batch_level_id === selectedLevel?.id && semester.intake_id === selectedLevel?.intake_id,
  ).sort((a, b) => a.semester_number - b.semester_number || a.attempt_number - b.attempt_number);
  const selectedSemester = semesters.find((semester) => semester.id === Number(form.cohort_semester_id));
  const selectedCourse = data.courses.find((course) => course.id === Number(form.academic_module_id));
  const batchSections = data.sections.filter((section) => section.batch_id === selectedBatch?.id);

  function closeEdit() {
    setEdit(null);
    setForm(blank);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedBatch || !selectedLevel || !selectedSemester || !selectedCourse) {
      setError("Select a batch, level / intake, semester, and course.");
      return;
    }
    if (batchSections.length && !form.section_ids.length) {
      setError("Select at least one section for this course.");
      return;
    }
    if (form.section_ids.some((id) => !batchSections.some((section) => section.id === id))) {
      setError("Select sections from the selected batch.");
      return;
    }
    const editing = edit;
    setSaving(true);
    setError("");
    const payload = {
      academic_module_id: selectedCourse.id,
      intake_id: selectedSemester.intake_id,
      batch_id: selectedSemester.batch_id,
      semester_number: selectedSemester.semester_number,

      section_ids: form.section_ids,
      is_active: form.is_active,
    };
    try {
      if (editing !== null) await api.patch(`/api/v1/academic/module-offerings/${editing}`, payload);
      else await api.post("/api/v1/academic/module-offerings", payload);
      setForm(blank);
      setEdit(null);
      await load();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to save course assignment."));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row: Assignment) {
    setTogglingId(row.id);
    setError("");
    try {
      await api.patch(`/api/v1/academic/module-offerings/${row.id}/activation?is_active=${!row.is_active}`);
      await load();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to change assignment status."));
    } finally {
      setTogglingId(null);
    }
  }

  function selectForEdit(row: Assignment) {
    const batch = data.batches.find((item) => item.id === row.batch_id);
    const level = batch?.levels.find((item) => item.intake_id === row.intake_id);
    const semester = data.semesters.find((item) => row.cohort_semester_id !== null
      ? item.id === row.cohort_semester_id
      : item.batch_id === row.batch_id && item.batch_level_id === level?.id && item.semester_number === row.semester_number);
    setError("");
    setEdit(row.id);
    setForm({
      academic_module_id: String(row.academic_module_id),
      batch_id: String(row.batch_id),
      batch_level_id: level ? String(level.id) : "",
      cohort_semester_id: semester ? String(semester.id) : "",
      section_ids: row.section_ids,
      is_active: row.is_active,
    });
  }

  const assignmentFields = (autoFocusFirst = false) => <>
    <label>
      <span className="field-label">Batch</span>
      <select autoFocus={autoFocusFirst} required className="w-full" disabled={loading || saving} value={form.batch_id} onChange={(event) => {
        setForm({ ...form, batch_id: event.target.value, batch_level_id: "", cohort_semester_id: "", academic_module_id: "", section_ids: [] });
      }}>
        <option value="">Select batch</option>
        {data.batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.name}</option>)}
      </select>
    </label>
    <label>
      <span className="field-label">Level / Intake</span>
      <select required className="w-full" disabled={!selectedBatch || loading || saving} value={form.batch_level_id} onChange={(event) => {
        setForm({ ...form, batch_level_id: event.target.value, cohort_semester_id: "", academic_module_id: "", section_ids: [] });
      }}>
        <option value="">Select level / intake</option>
        {levels.map((level) => <option key={level.id} value={level.id}>{levelLabel(level)}</option>)}
      </select>
      {selectedBatch && !levels.length && <span className="mt-1 block text-sm text-amber-300">No Level / Intake records exist for this batch yet.</span>}
    </label>
    <label>
      <span className="field-label">Semester</span>
      <select required className="w-full" disabled={!selectedLevel || loading || saving} value={form.cohort_semester_id} onChange={(event) => {
        setForm({ ...form, cohort_semester_id: event.target.value, academic_module_id: "", section_ids: [] });
      }}>
        <option value="">Select semester</option>
        {semesters.map((semester) => <option key={semester.id} value={semester.id}>{semesterLabel(semester)}{semester.attempt_number > 1 ? ` · Attempt ${semester.attempt_number}` : ""}</option>)}
      </select>
      {selectedLevel && !semesters.length && <span className="mt-1 block text-sm text-amber-300">No semesters exist for this Level / Intake yet.</span>}
    </label>
    <label className="min-w-0">
      <span className="field-label">Course</span>
      <select required className="w-full min-w-0" disabled={!selectedSemester || loading || saving} value={form.academic_module_id} onChange={(event) => {
        setForm({ ...form, academic_module_id: event.target.value, section_ids: event.target.value ? batchSections.map((section) => section.id) : [] });
      }}>
        <option value="">Select course</option>
        {data.courses.map((course) => <option key={course.id} value={course.id}>{courseLabel(course)}</option>)}
      </select>
      {selectedCourse && <span className="mt-1 block break-words text-sm text-slate-300">{courseLabel(selectedCourse)}</span>}
    </label>

    <fieldset className="rounded-lg border border-slate-700 bg-slate-950/70 p-3" disabled={!selectedSemester || !selectedCourse || loading || saving}>
      <legend className="px-1 text-sm font-medium text-slate-100">Sections</legend>
      <p className="text-sm text-slate-400">Choose the sections in this batch that receive the course.</p>
      {batchSections.length ? <div className="mt-3 flex flex-wrap gap-3">{batchSections.map((section) => <label key={section.id} className="flex items-center gap-2"><input type="checkbox" checked={form.section_ids.includes(section.id)} onChange={(event) => setForm({ ...form, section_ids: event.target.checked ? [...form.section_ids, section.id] : form.section_ids.filter((id) => id !== section.id) })} /><Badge tone="neutral">{section.name}</Badge></label>)}</div> : <p className="mt-3 text-sm text-amber-300">{selectedBatch ? "No sections exist for this batch yet. Sections added later will receive this course automatically." : "Select a batch to see its sections."}</p>}
    </fieldset>

    <label className="flex items-center gap-2 self-end">
      <input type="checkbox" disabled={saving} checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
      <span className="text-sm font-medium">Active</span>
    </label>
  </>;

  return <div className="max-w-7xl">
    <PageHeader title="Course Assignments" description="Assign courses to a batch and semester, and select which sections take each course." />

    <section className="panel p-5" aria-labelledby="create-course-assignment-title">
      <div className="mb-5"><h2 id="create-course-assignment-title" className="text-lg font-semibold">Assign Course</h2><p className="mt-1 text-sm text-slate-400">Choose the Batch, Level / Intake, Semester, Course, and sections for this assignment.</p></div>
      <form onSubmit={submit} className="grid max-w-3xl gap-4">
        {assignmentFields()}
        <div><Button type="submit" loading={saving} disabled={loading || !selectedSemester || !selectedCourse}>Assign Course</Button></div>
      </form>
    </section>

    {error && edit === null && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}

    <div className="mt-7">
      {loading ? <LoadingState label="Loading course assignments…" /> : !rows.length ? <EmptyState title="No course assignments yet" description="Assign a course to a semester and its batch sections before building or importing routines." /> : (
        <div className="table-wrap" role="region" aria-label="Scrollable records" tabIndex={0}>
          <table>
            <thead><tr><th>Course</th><th>Level / Intake</th><th>Batch</th><th>Semester</th><th>Sections</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{rows.map((row) => {
              const level = data.batches.find((batch) => batch.id === row.batch_id)?.levels.find((item) => item.intake_id === row.intake_id);
              const assignmentSemester = data.semesters.find((semester) => semester.id === row.cohort_semester_id);
              return <tr key={row.id}>
              <td className="font-medium text-slate-100">{row.module_code} — {row.module_title}</td>
              <td>{level ? levelLabel(level) : row.intake_code}</td><td>{row.batch_name}</td><td>{assignmentSemester ? semesterLabel(assignmentSemester) : `Semester ${row.semester_number}`}</td>
              <td>{row.section_names.length ? <span>{row.section_names.join(" + ")} <span className="text-slate-500">({row.section_names.length} total)</span></span> : <span className="text-slate-500">Awaiting sections</span>}</td>
              <td><Badge tone={row.is_active ? "success" : "neutral"}>{row.is_active ? "Active" : "Inactive"}</Badge></td>
              <td><div className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => selectForEdit(row)}>Edit</Button><Button type="button" size="sm" variant="outline" loading={togglingId === row.id} disabled={togglingId !== null} onClick={() => setPendingToggle(row)}>{row.is_active ? "Deactivate" : "Activate"}</Button></div></td>
            </tr>; })}</tbody>
          </table>
        </div>
      )}
    </div>

    {edit !== null && <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-course-assignment-title">
      <button type="button" aria-label="Close edit dialog" className="absolute inset-0 bg-black/70" onClick={closeEdit} disabled={saving} />
      <section className="panel relative max-h-[90dvh] w-full max-w-3xl overflow-y-auto p-6">
        <div className="mb-5"><h2 id="edit-course-assignment-title" className="text-xl font-semibold">Edit course assignment</h2><p className="mt-1 text-sm text-slate-400">Update the course assignment and its status, then save your changes.</p></div>
        {error && <SystemFeedback className="mb-4" tone="danger" title="Unable to save this assignment" description={error} />}
        <form onSubmit={submit} className="grid gap-4">
          {assignmentFields(true)}
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={closeEdit} disabled={saving}>Cancel</Button><Button type="submit" loading={saving} disabled={loading || !selectedSemester || !selectedCourse}>Save changes</Button></div>
        </form>
      </section>
    </div>}
    <ConfirmDialog open={pendingToggle !== null} title={`${pendingToggle?.is_active ? "Deactivate" : "Activate"} this course assignment?`} description={pendingToggle?.is_active ? "Sections will no longer be able to use this assignment for new routine entries until it is activated again." : "Selected sections will be able to use this assignment in routine and attendance workflows."} confirmLabel={pendingToggle?.is_active ? "Deactivate assignment" : "Activate assignment"} tone={pendingToggle?.is_active ? "danger" : "primary"} onClose={() => setPendingToggle(null)} onConfirm={async () => { if (pendingToggle) await toggle(pendingToggle); setPendingToggle(null); }} />
  </div>;
}
