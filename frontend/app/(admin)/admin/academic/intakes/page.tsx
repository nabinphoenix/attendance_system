"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type Level = { id: number; level_number: number; intake_code: string; intake_name: string | null };
type Batch = { id: number; name: string; levels: Level[] };
type Semester = {
  id: number; batch_id: number; batch_level_id: number; semester_number: number;
  display_name: string; start_date: string; end_date: string; calendar_uploaded: boolean;
};
type IntakeSetup = { batch: Batch; level: Level; semesters: Semester[] };
type SemesterDraft = { display_name: string; start_date: string; end_date: string; calendar: File | null };

const blankForm = { batch_id: "", level_number: "", intake_code: "", intake_name: "" };
const blankSemester = (semesterNumber: number): SemesterDraft => ({
  display_name: `Semester ${semesterNumber}`, start_date: "", end_date: "", calendar: null,
});
const levelSemesterNumbers = (levelNumber: number) => [levelNumber * 2 - 1, levelNumber * 2];

export default function Page() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [form, setForm] = useState(blankForm);
  const [semesterDrafts, setSemesterDrafts] = useState<SemesterDraft[]>([]);
  const [editingSemester, setEditingSemester] = useState<Semester | null>(null);
  const [editDraft, setEditDraft] = useState<SemesterDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [batchResponse, semesterResponse] = await Promise.all([
        api.get<Batch[]>("/api/v1/academic/batches"),
        api.get<Semester[]>("/api/v1/academic/cohort-semesters"),
      ]);
      setBatches(batchResponse.data);
      setSemesters(semesterResponse.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load Level and Intake setup.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const selectedBatch = batches.find((batch) => batch.id === Number(form.batch_id));
  const selectedLevelNumber = Number(form.level_number);
  const configuredLevels = new Set(selectedBatch?.levels.map((level) => level.level_number) ?? []);
  const expectedSemesterNumbers = selectedLevelNumber ? levelSemesterNumbers(selectedLevelNumber) : [];
  const intakeSetups = useMemo<IntakeSetup[]>(() => batches.flatMap((batch) => batch.levels.map((level) => ({
    batch,
    level,
    semesters: semesters.filter((semester) => semester.batch_level_id === level.id)
      .sort((a, b) => a.semester_number - b.semester_number),
  }))), [batches, semesters]);

  function chooseLevel(value: string) {
    const levelNumber = Number(value);
    setForm((current) => ({ ...current, level_number: value }));
    setSemesterDrafts(levelNumber ? levelSemesterNumbers(levelNumber).map(blankSemester) : []);
  }

  function updateDraft(index: number, field: keyof SemesterDraft, value: string | File | null) {
    setSemesterDrafts((current) => current.map((draft, draftIndex) => draftIndex === index ? { ...draft, [field]: value } : draft));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedBatch || !selectedLevelNumber || semesterDrafts.length !== 2) return;
    if (semesterDrafts.some((draft) => !draft.display_name.trim() || !draft.start_date || !draft.end_date || !draft.calendar)) {
      setError("Provide a display name, start date, end date, and Academic Calendar PDF for both semesters.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const body = new FormData();
    body.append("batch_id", String(selectedBatch.id));
    body.append("level_number", String(selectedLevelNumber));
    body.append("intake_code", form.intake_code.trim());
    if (form.intake_name.trim()) body.append("intake_name", form.intake_name.trim());
    const semesterDetails = semesterDrafts.map(({ display_name, start_date, end_date }) => ({ display_name: display_name.trim(), start_date, end_date }));
    body.append("semester_details", JSON.stringify(semesterDetails));
    body.append("semester_one_calendar", semesterDrafts[0].calendar as File);
    body.append("semester_two_calendar", semesterDrafts[1].calendar as File);
    try {
      await api.post("/api/v1/academic/levels/with-calendars", body);
      setMessage(`Level ${selectedLevelNumber} · ${form.intake_code.trim()} created with Semesters ${expectedSemesterNumbers.join(" and ")}.`);
      setForm(blankForm);
      setSemesterDrafts([]);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to create this Level and Intake Code.");
    } finally {
      setSaving(false);
    }
  }

  function openSemesterEditor(semester: Semester) {
    setEditingSemester(semester);
    setEditDraft({ display_name: semester.display_name || `Semester ${semester.semester_number}`, start_date: semester.start_date, end_date: semester.end_date, calendar: null });
    setError("");
  }

  async function saveSemester(event: FormEvent) {
    event.preventDefault();
    if (!editingSemester || !editDraft) return;
    setSaving(true);
    setError("");
    try {
      await api.patch(`/api/v1/academic/cohort-semesters/${editingSemester.id}`, {
        display_name: editDraft.display_name.trim(), start_date: editDraft.start_date, end_date: editDraft.end_date,
      });
      if (editDraft.calendar) {
        const body = new FormData();
        body.append("file", editDraft.calendar);
        await api.put(`/api/v1/academic/semester-resources/semesters/${editingSemester.id}/calendar`, body);
      }
      setEditingSemester(null);
      setEditDraft(null);
      setMessage(`Semester ${editingSemester.semester_number} details updated.`);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to update this Semester.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="max-w-6xl">
    <PageHeader title="Levels & Intake Codes" description="For each Batch and Level, enter its Intake Code and the real details for the two corresponding semesters." />
    {message && <SystemFeedback className="mb-4" tone="success" title="Academic setup saved" description={message} />}
    {error && !editingSemester && <div className="mb-4"><ErrorState title="Unable to complete this action" description={error} onRetry={() => void load()} /></div>}

    <section className="panel p-5" aria-labelledby="create-intake-title">
      <div className="mb-5">
        <h2 id="create-intake-title" className="text-lg font-semibold">Create Level / Intake</h2>
        <p className="mt-1 text-sm text-slate-400">Level 1 creates Semesters 1–2, Level 2 creates 3–4, and Level 3 creates 5–6. Dates and Academic Calendars are supplied by you.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <label><span className="field-label">Batch</span><select className="w-full" required value={form.batch_id} onChange={(event) => { setForm({ ...form, batch_id: event.target.value, level_number: "" }); setSemesterDrafts([]); }}><option value="">Select batch</option>{batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.name}</option>)}</select></label>
        <label><span className="field-label">Level / Year</span><select className="w-full" required disabled={!selectedBatch} value={form.level_number} onChange={(event) => chooseLevel(event.target.value)}><option value="">Select level</option>{[1, 2, 3].map((level) => <option key={level} value={level} disabled={configuredLevels.has(level)}>Level {level}{configuredLevels.has(level) ? " (already configured)" : ""}</option>)}</select></label>
        <label><span className="field-label">Intake Code</span><input className="w-full" required maxLength={50} value={form.intake_code} onChange={(event) => setForm({ ...form, intake_code: event.target.value })} /></label>
        <label><span className="field-label">Intake Name (optional)</span><input className="w-full" maxLength={100} value={form.intake_name} onChange={(event) => setForm({ ...form, intake_name: event.target.value })} /></label>
        {semesterDrafts.map((draft, index) => <fieldset key={expectedSemesterNumbers[index]} className="rounded-lg border border-slate-700 bg-slate-950/50 p-4 md:col-span-2">
          <legend className="px-1 font-semibold text-slate-100">Semester {expectedSemesterNumbers[index]}</legend>
          <div className="grid gap-4 md:grid-cols-2">
            <label><span className="field-label">Display Name</span><input className="w-full" required value={draft.display_name} onChange={(event) => updateDraft(index, "display_name", event.target.value)} /></label>
            <label><span className="field-label">Academic Calendar</span><input className="w-full" required type="file" accept="application/pdf,.pdf" onChange={(event) => updateDraft(index, "calendar", event.target.files?.[0] ?? null)} /><span className="mt-1 block text-xs text-slate-400">PDF only, up to 10 MB.</span></label>
            <label><span className="field-label">Start Date</span><input className="w-full" required type="date" value={draft.start_date} onChange={(event) => updateDraft(index, "start_date", event.target.value)} /></label>
            <label><span className="field-label">End Date</span><input className="w-full" required type="date" value={draft.end_date} onChange={(event) => updateDraft(index, "end_date", event.target.value)} /></label>
          </div>
        </fieldset>)}
        <div className="md:col-span-2"><Button type="submit" loading={saving} disabled={!selectedLevelNumber}>Create Intake & Semesters</Button></div>
      </form>
    </section>

    <section className="mt-7">
      <h2 className="mb-3 text-lg font-semibold">Configured Levels & Intake Codes</h2>
      {loading ? <LoadingState label="Loading academic setup" /> : <div className="table-wrap" role="region" aria-label="Configured Levels and Intake Codes" tabIndex={0}><table><thead><tr><th>Batch</th><th>Level / Year</th><th>Intake Code</th><th>Semesters</th></tr></thead><tbody>
        {intakeSetups.map(({ batch, level, semesters: levelSemesters }) => <tr key={level.id}><td>{batch.name}</td><td>Level {level.level_number}</td><td>{level.intake_code}{level.intake_name ? <span className="block text-xs text-slate-400">{level.intake_name}</span> : null}</td><td>{levelSemesters.length ? levelSemesters.map((semester) => <div key={semester.id} className="mb-2 last:mb-0"><div className="flex flex-wrap items-center gap-2"><span className="font-medium text-slate-100">Semester {semester.semester_number}: {semester.display_name || `Semester ${semester.semester_number}`}</span><Button type="button" size="sm" variant="ghost" onClick={() => openSemesterEditor(semester)}>Edit</Button></div><span className="text-sm text-slate-400">{semester.start_date} to {semester.end_date} · {semester.calendar_uploaded ? "Academic Calendar uploaded" : "Academic Calendar missing"}</span></div>) : <span className="text-amber-300">Semester details missing</span>}</td></tr>)}
        {!intakeSetups.length && <tr><td colSpan={4} className="p-0"><EmptyState title="No Levels or Intake Codes configured" description="Create the first Level / Intake for a Batch above." /></td></tr>}
      </tbody></table></div>}
    </section>

    {editingSemester && editDraft && <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-semester-title">
      <button type="button" aria-label="Close semester editor" className="absolute inset-0 bg-black/70" onClick={() => { if (!saving) { setEditingSemester(null); setEditDraft(null); } }} />
      <section className="panel relative w-full max-w-xl p-6"><div className="mb-5"><h2 id="edit-semester-title" className="text-xl font-semibold">Edit Semester {editingSemester.semester_number}</h2><p className="mt-1 text-sm text-slate-400">The semester number is fixed. Its display name, dates, and Academic Calendar are specific to this Batch and Intake.</p></div>
        {error && <SystemFeedback className="mb-4" tone="danger" title="Unable to update Semester" description={error} />}
        <form onSubmit={saveSemester} className="grid gap-4"><label><span className="field-label">Display Name</span><input className="w-full" required value={editDraft.display_name} onChange={(event) => setEditDraft({ ...editDraft, display_name: event.target.value })} /></label><label><span className="field-label">Start Date</span><input className="w-full" required type="date" value={editDraft.start_date} onChange={(event) => setEditDraft({ ...editDraft, start_date: event.target.value })} /></label><label><span className="field-label">End Date</span><input className="w-full" required type="date" value={editDraft.end_date} onChange={(event) => setEditDraft({ ...editDraft, end_date: event.target.value })} /></label><label><span className="field-label">Replace Academic Calendar (optional)</span><input className="w-full" type="file" accept="application/pdf,.pdf" onChange={(event) => setEditDraft({ ...editDraft, calendar: event.target.files?.[0] ?? null })} /></label><div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => { setEditingSemester(null); setEditDraft(null); }} disabled={saving}>Cancel</Button><Button type="submit" loading={saving}>Save Semester</Button></div></form>
      </section>
    </div>}
  </div>;
}