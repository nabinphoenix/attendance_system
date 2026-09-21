"use client";

import Link from "next/link";
import { isAxiosError } from "axios";
import { type FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type Calendar = { id: number; filename: string; size_bytes: number; uploaded_at: string };
type Semester = {
  id: number; intake_name: string; batch_name: string; semester_number: number;
  attempt_number: number; start_date: string; end_date: string; calendar: Calendar | null;
};
type Teacher = { id: number; name: string; employee_code: string };
type Feedback = {
  id: number; teacher_id: number; teacher_name: string; title: string; form_url: string | null;
  opens_on: string; closes_on: string; is_published: boolean;
  status: "draft" | "scheduled" | "open" | "closed";
};
const base = "/api/v1/academic/semester-resources/semesters";
const fieldClass = "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm";
const linkClass = "inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-400/40 px-4 py-2 text-sm font-semibold text-emerald-300 hover:bg-emerald-400/10";
const statusClass = {
  draft: "bg-slate-700 text-slate-200", scheduled: "bg-sky-500/15 text-sky-300",
  open: "bg-emerald-500/15 text-emerald-300", closed: "bg-amber-500/15 text-amber-300",
};

function errorMessage(error: unknown, fallback: string): string {
  if (!isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg ?? fallback).join(". ");
  return fallback;
}

function defaultWindow(semester: Semester) {
  const start = Date.parse(semester.start_date + "T00:00:00Z");
  const end = Date.parse(semester.end_date + "T00:00:00Z");
  const midpoint = start + Math.floor((end - start) / 86400000 / 2) * 86400000;
  return {
    opens_on: new Date(midpoint).toISOString().slice(0, 10),
    closes_on: new Date(Math.min(end, midpoint + 13 * 86400000)).toISOString().slice(0, 10),
  };
}

function FeedbackEditor({ semester, teacher, existing, onSaved, onBusy, disabled }: {
  semester: Semester; teacher: Teacher; existing?: Feedback;
  onSaved: () => void; onBusy: (busy: boolean) => void; disabled: boolean;
}) {
  const [draft, setDraft] = useState({
    title: existing?.title ?? "Mid-semester teacher feedback", form_url: existing?.form_url ?? "",
    opens_on: existing?.opens_on ?? defaultWindow(semester).opens_on,
    closes_on: existing?.closes_on ?? defaultWindow(semester).closes_on,
    is_published: existing?.is_published ?? false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true); onBusy(true); setError("");
    try {
      await api.put(`${base}/${semester.id}/feedback/${teacher.id}`, draft);
      onSaved();
    } catch (error) {
      setError(errorMessage(error, "Unable to save this feedback form."));
    } finally {
      setSaving(false); onBusy(false);
    }
  }
  return <form onSubmit={save} className="mt-4 space-y-4 rounded-xl border border-slate-700 p-4">
    <fieldset disabled={disabled || saving} className="space-y-4">
    <h3 className="font-semibold">{existing ? "Edit feedback" : "Set up feedback"} for {teacher.name}</h3>
    <label className="block text-sm">Title<input className={fieldClass + " mt-1"} required maxLength={200} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
    <label className="block text-sm">Google Forms responder link<input className={fieldClass + " mt-1"} required type="url" maxLength={2048} placeholder="https://forms.gle/..." value={draft.form_url} onChange={e => setDraft({ ...draft, form_url: e.target.value })} /></label>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="block text-sm">Opens on<input className={fieldClass + " mt-1"} required type="date" min={semester.start_date} max={semester.end_date} value={draft.opens_on} onChange={e => setDraft({ ...draft, opens_on: e.target.value })} /></label>
      <label className="block text-sm">Closes on<input className={fieldClass + " mt-1"} required type="date" min={draft.opens_on || semester.start_date} max={semester.end_date} value={draft.closes_on} onChange={e => setDraft({ ...draft, closes_on: e.target.value })} /></label>
    </div>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.is_published} onChange={e => setDraft({ ...draft, is_published: e.target.checked })} />Publish to students during this window</label>
    <p className="text-xs leading-5 text-slate-400">Dates control availability in AntimBench. Publish the form in Google Forms and configure its responder access, collection dates, and one-response limit there. Responses remain in Google Forms.</p>
    <a href="https://support.google.com/docs/answer/2839588" target="_blank" rel="noopener noreferrer" className="block text-sm text-emerald-300 underline">Google Forms sharing guide</a>
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    <Button type="submit" loading={saving}>Save feedback form</Button>
    </fieldset>
  </form>;
}

export default function SemesterResourcesPage({ role }: { role: "admin" | "student" | "teacher" }) {
  const admin = role === "admin";
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [teacherId, setTeacherId] = useState("");
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [detailsVersion, setDetailsVersion] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<"calendar" | Feedback | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const semester = semesters.find(row => String(row.id) === selectedId);
  const teacher = teachers.find(row => String(row.id) === teacherId);

  useEffect(() => {
    let active = true;
    setLoading(true); setLoadError("");
    api.get<Semester[]>(base).then(response => {
      if (!active) return;
      setSemesters(response.data);
      setSelectedId(current => response.data.some(row => String(row.id) === current) ? current : String(response.data[0]?.id ?? ""));
    }).catch(error => { if (active) setLoadError(errorMessage(error, "Unable to load semester resources.")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  useEffect(() => {
    let active = true;
    setFeedback([]); setTeachers([]); setDetailsError("");
    if (!selectedId || role === "teacher") return;
    setDetailsLoading(true);
    Promise.all([
      api.get<Feedback[]>(`${base}/${selectedId}/feedback`),
      admin ? api.get<Teacher[]>(`${base}/${selectedId}/teachers`) : Promise.resolve({ data: [] as Teacher[] }),
    ]).then(([forms, teacherOptions]) => {
      if (!active) return;
      setFeedback(forms.data);
      const choices = [...teacherOptions.data];
      for (const form of forms.data) {
        if (!choices.some(item => item.id === form.teacher_id)) choices.push({ id: form.teacher_id, name: form.teacher_name, employee_code: "" });
      }
      setTeachers(choices);
    }).catch(error => { if (active) setDetailsError(errorMessage(error, "Unable to load feedback forms.")); })
      .finally(() => { if (active) setDetailsLoading(false); });
    return () => { active = false; };
  }, [selectedId, admin, role, detailsVersion]);

  function changeSemester(value: string) {
    setSelectedId(value); setFeedback([]); setTeachers([]); setDetailsLoading(role !== "teacher"); setTeacherId(""); setFile(null); setMessage(""); setError(""); setRemoving(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  function updateCalendar(calendar: Calendar | null) {
    setSemesters(current => current.map(row => row.id === semester?.id ? { ...row, calendar } : row));
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!semester || !file) return;
    setMessage(""); setError("");
    if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 10 * 1024 * 1024 || !file.size) {
      setError("Choose a PDF file between 1 byte and 10 MB."); return;
    }
    setBusy(true);
    try {
      const body = new FormData(); body.append("file", file);
      const response = await api.put<Calendar>(`${base}/${semester.id}/calendar`, body);
      updateCalendar(response.data); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      setMessage("Academic calendar saved.");
    } catch (error) {
      setError(errorMessage(error, "Unable to upload the academic calendar."));
    } finally { setBusy(false); }
  }

  async function download() {
    if (!semester?.calendar) return;
    setBusy(true); setError("");
    try { await downloadFile(`${base}/${semester.id}/calendar`, semester.calendar.filename); }
    catch (error) { setError(errorMessage(error, "Unable to download the academic calendar.")); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!semester || !removing) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const suffix = removing === "calendar" ? "calendar" : `feedback/${removing.teacher_id}`;
      await api.delete(`${base}/${semester.id}/${suffix}`);
      if (removing === "calendar") updateCalendar(null);
      else { setTeacherId(""); setDetailsVersion(value => value + 1); }
      setMessage(removing === "calendar" ? "Academic calendar removed." : "Feedback form removed.");
    } catch (error) { setError(errorMessage(error, "Unable to remove this resource.")); }
    finally { setBusy(false); }
  }

  return <div className="max-w-6xl">
    <PageHeader title={role === "teacher" ? "Academic calendars" : "Semester resources"} description={admin
      ? "Manage academic calendar PDFs and one mid-semester Google Form for each teacher."
      : role === "teacher" ? "Download the academic calendars for your teaching semesters."
      : "Find your semester calendar and share feedback with your teachers."} />
    {loading ? <LoadingState label="Loading semester resources" /> : loadError
      ? <ErrorState description={loadError} onRetry={() => setReload(value => value + 1)} />
      : !semesters.length ? <EmptyState title="No semesters available" description={admin ? "Create a dated cohort semester to add its calendar and teacher feedback." : "Your semester resources will appear once your semester is assigned."} action={admin && <Link className={linkClass} href="/admin/academic/promotions">Set up semesters</Link>} />
      : <>
        <label className="mb-6 block max-w-3xl text-sm font-medium">Semester
          <select className={fieldClass + " mt-2"} value={selectedId} disabled={busy} onChange={e => changeSemester(e.target.value)}>
            {semesters.map(row => <option key={row.id} value={row.id}>{row.intake_name} / {row.batch_name} / Semester {row.semester_number}{row.attempt_number > 1 ? ` / Attempt ${row.attempt_number}` : ""} / {row.start_date} to {row.end_date}</option>)}
          </select>
        </label>
        {message && <p role="status" className="mb-4 rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300">{message}</p>}
        {error && <p role="alert" className="mb-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
        {semester && <div className="space-y-6">
          <section className="panel p-5 sm:p-6" aria-labelledby="calendar-title">
            <h2 id="calendar-title" className="text-xl font-semibold">Academic calendar</h2>
            {semester.calendar ? <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-700 p-4">
              <div className="min-w-0"><p className="break-all font-medium">{semester.calendar.filename}</p><p className="mt-1 text-xs text-slate-400">PDF / {(semester.calendar.size_bytes / 1024).toFixed(1)} KB / Updated {new Date(semester.calendar.uploaded_at).toLocaleDateString()}</p></div>
              <div className="flex gap-2"><Button variant="outline" disabled={busy} onClick={() => void download()}>Download PDF</Button>{admin && <Button variant="danger" disabled={busy} onClick={() => setRemoving("calendar")}>Remove</Button>}</div>
            </div> : <p className="mt-3 text-sm text-slate-400">No academic calendar has been uploaded for this semester.</p>}
            {admin && <form onSubmit={upload} className="mt-5 flex flex-wrap items-end gap-3">
              <label className="block min-w-0 flex-1 text-sm">{semester.calendar ? "Replace calendar PDF" : "Upload calendar PDF"}<input ref={fileInput} className={fieldClass + " mt-2"} disabled={busy} required type="file" accept=".pdf,application/pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} /><span className="mt-1 block text-xs text-slate-400">PDF only, up to 10 MB. One calendar per semester; uploading replaces the current file.</span></label>
              <Button type="submit" disabled={!file || busy}>{semester.calendar ? "Replace PDF" : "Upload PDF"}</Button>
            </form>}
          </section>
          {role !== "teacher" && <section className="panel p-5 sm:p-6" aria-labelledby="feedback-title">
            <h2 id="feedback-title" className="text-xl font-semibold">Mid-semester teacher feedback</h2>
            <p className="mt-2 text-sm text-slate-400">{admin ? "Choose a teacher assigned to this semester. The suggested window starts at the semester midpoint." : "Available forms open in Google Forms. Responses are submitted directly to the form owner."}</p>
            {detailsLoading ? <LoadingState label="Loading teacher feedback" /> : detailsError ? <ErrorState description={detailsError} onRetry={() => setDetailsVersion(value => value + 1)} /> : <>
              {admin && <>
                <p className="mt-3 text-sm text-slate-400">{feedback.length} of {teachers.length} teachers have a feedback form.</p>
                <label className="mt-4 block text-sm font-medium">Teacher<select className={fieldClass + " mt-2"} disabled={busy} value={teacherId} onChange={e => setTeacherId(e.target.value)}><option value="">Choose a teacher to set up or edit feedback</option>{teachers.map(row => <option key={row.id} value={row.id}>{row.name}{row.employee_code ? ` (${row.employee_code})` : ""}{feedback.some(form => form.teacher_id === row.id) ? " - Configured" : " - Not configured"}</option>)}</select></label>
                {!teachers.length && <p className="mt-3 text-sm text-slate-400">Assign teachers in the <Link href="/admin/routine" className="text-emerald-300 underline">semester routine</Link> before adding feedback.</p>}
                {teacher && <FeedbackEditor key={`${semester.id}-${teacher.id}-${detailsVersion}`} semester={semester} teacher={teacher} disabled={busy} existing={feedback.find(row => row.teacher_id === teacher.id)} onBusy={setBusy} onSaved={() => { setMessage("Feedback form saved."); setDetailsVersion(value => value + 1); }} />}
              </>}
              <div className="mt-5 grid gap-4 md:grid-cols-2">{feedback.map(row => <article key={row.id} className="rounded-xl border border-slate-700 p-4">
                <div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{row.teacher_name}</h3><span className={`rounded-full px-2.5 py-1 text-xs capitalize ${statusClass[row.status]}`}>{row.status}</span></div>
                <p className="mt-2 text-sm">{row.title}</p><p className="mt-1 text-xs text-slate-400">{row.opens_on} to {row.closes_on}</p>
                <div className="mt-4 flex flex-wrap gap-2">{row.form_url && <a href={row.form_url} target="_blank" rel="noopener noreferrer" className={linkClass}>{admin ? "Open Google Form" : "Give feedback"}</a>}{admin && <><Button variant="outline" disabled={busy} onClick={() => setTeacherId(String(row.teacher_id))}>Edit</Button><Button variant="danger" disabled={busy} onClick={() => setRemoving(row)}>Remove</Button></>}</div>
                {!admin && row.status === "scheduled" && <p className="mt-3 text-sm text-slate-400">Available from {row.opens_on}.</p>}
                {!admin && row.status === "closed" && <p className="mt-3 text-sm text-slate-400">The feedback window has ended.</p>}
              </article>)}</div>
              {!feedback.length && <EmptyState title="No feedback forms available" description={admin ? "Select a teacher above to add their Google Form." : "Published feedback forms for your current teachers will appear here."} />}
            </>}
          </section>}
        </div>}
      </>}
    <ConfirmDialog open={removing !== null} title={removing === "calendar" ? "Remove academic calendar?" : "Remove feedback form?"} description={removing === "calendar" ? "Students and teachers will no longer be able to download this PDF." : "The form link will be removed from this semester. Responses already collected in Google Forms remain there."} confirmLabel="Remove" tone="danger" onClose={() => { if (!busy) setRemoving(null); }} onConfirm={remove} />
  </div>;
}
