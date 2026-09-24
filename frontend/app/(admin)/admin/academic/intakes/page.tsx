"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type Level = { id: number; level_number: number; intake_code: string; intake_name: string | null };
type Batch = { id: number; name: string; levels: Level[] };
type Semester = { id: number; batch_level_id: number; semester_number: number; start_date: string; end_date: string };
type IntakeSetup = { batch: Batch; level: Level; semesters: Semester[] };

const blankForm = { batch_id: "", level_number: "", intake_code: "", intake_name: "" };

export default function Page() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [form, setForm] = useState(blankForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [batchResponse, semesterResponse] = await Promise.all([
        api.get("/api/v1/academic/batches"),
        api.get("/api/v1/academic/cohort-semesters"),
      ]);
      setBatches(batchResponse.data);
      setSemesters(semesterResponse.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load intake setup.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const selectedBatch = batches.find((batch) => batch.id === Number(form.batch_id));
  const configuredLevels = new Set(selectedBatch?.levels.map((level) => level.level_number) ?? []);
  const intakeSetups = useMemo<IntakeSetup[]>(() => batches.flatMap((batch) => batch.levels.map((level) => ({
    batch,
    level,
    semesters: semesters.filter((semester) => semester.batch_level_id === level.id)
      .sort((a, b) => a.semester_number - b.semester_number),
  }))), [batches, semesters]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await api.post("/api/v1/academic/levels", {
        batch_id: Number(form.batch_id),
        level_number: Number(form.level_number),
        intake_code: form.intake_code.trim(),
        intake_name: form.intake_name.trim() || null,
      });
      const level = response.data as Level;
      setMessage(`Intake Code ${level.intake_code} created with Semesters ${level.level_number * 2 - 1} and ${level.level_number * 2}.`);
      setForm(blankForm);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to create this Intake Code.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="max-w-6xl">
    <PageHeader title="Intake setup" description="Create an Intake Code for a Batch and Level. Its two semester records are created automatically." />
    {message && <p className="mb-4 text-sm text-emerald-400">{message}</p>}
    {error && <div className="mb-4"><ErrorState title="Unable to complete this action" description={error} onRetry={() => void load()} /></div>}

    <section className="panel p-5" aria-labelledby="create-intake-title">
      <div className="mb-5">
        <h2 id="create-intake-title" className="text-lg font-semibold">Create Intake Code</h2>
        <p className="mt-1 text-sm text-slate-400">Level 1 creates Semesters 1?2, Level 2 creates 3?4, and Level 3 creates 5?6.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <label><span className="field-label">Batch</span><select className="w-full" required value={form.batch_id} onChange={(event) => setForm({ ...form, batch_id: event.target.value, level_number: "" })}><option value="">Select batch</option>{batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.name}</option>)}</select></label>
        <label><span className="field-label">Level / Year</span><select className="w-full" required disabled={!selectedBatch} value={form.level_number} onChange={(event) => setForm({ ...form, level_number: event.target.value })}><option value="">Select level</option>{[1, 2, 3].map((level) => <option key={level} value={level} disabled={configuredLevels.has(level)}>Level {level}{configuredLevels.has(level) ? " (already configured)" : ""}</option>)}</select></label>
        <label><span className="field-label">Intake Code</span><input className="w-full" required maxLength={50} value={form.intake_code} onChange={(event) => setForm({ ...form, intake_code: event.target.value })} /></label>
        <label><span className="field-label">Intake Name (optional)</span><input className="w-full" maxLength={100} value={form.intake_name} onChange={(event) => setForm({ ...form, intake_name: event.target.value })} /></label>
        <div className="md:col-span-2"><Button type="submit" loading={saving}>Create Intake Code and 2 Semesters</Button></div>
      </form>
    </section>

    <section className="mt-7">
      <h2 className="mb-3 text-lg font-semibold">Configured Intake Codes</h2>
      {loading ? <LoadingState label="Loading intake setup" /> : <div className="table-wrap" role="region" aria-label="Configured intake codes" tabIndex={0}><table><thead><tr><th>Batch</th><th>Level / Year</th><th>Intake Code</th><th>Automatic Semesters</th></tr></thead><tbody>
        {intakeSetups.map(({ batch, level, semesters: levelSemesters }) => <tr key={level.id}><td>{batch.name}</td><td>Level {level.level_number}</td><td>{level.intake_code}{level.intake_name ? <span className="block text-xs text-slate-400">{level.intake_name}</span> : null}</td><td>{levelSemesters.map((semester) => <div key={semester.id}>Semester {semester.semester_number}: {semester.start_date} to {semester.end_date}</div>)}</td></tr>)}
        {!intakeSetups.length && <tr><td colSpan={4} className="p-0"><EmptyState title="No Intake Codes configured" description="Create the first Intake Code for a Batch and Level above." /></td></tr>}
      </tbody></table></div>}
    </section>
  </div>;
}
