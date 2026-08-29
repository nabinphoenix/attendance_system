"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

const blank = { academic_module_id: "", intake_id: "", batch_id: "", semester_number: "", is_active: true };

export default function Page() {
  const [data, setData] = useState<Record<string, any[]>>({});
  const [rows, setRows] = useState<any[]>([]);
  const [form, setForm] = useState<any>(blank);
  const [edit, setEdit] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      const names = ["modules", "intakes", "batches", "sections", "module-offerings"];
      const responses = await Promise.all(names.map((name) => api.get(`/api/v1/academic/${name}`)));
      setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data])));
      setRows(responses[4].data);
      setError("");
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load module offerings.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const cohortSections = useMemo(
    () => (data.sections || []).filter(
      (section) =>
        (!form.batch_id || section.batch_id === Number(form.batch_id)) &&
        (!form.intake_id || section.intake_id === null || section.intake_id === Number(form.intake_id)) &&
        (!form.semester_number || section.semester_number === null || section.semester_number === Number(form.semester_number)),
    ),
    [data.sections, form.batch_id, form.intake_id, form.semester_number],
  );

  function closeEdit() {
    setEdit(null);
    setForm(blank);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const editing = edit;
    setSaving(true);
    setError("");
    const payload = {
      ...form,
      academic_module_id: Number(form.academic_module_id),
      intake_id: Number(form.intake_id),
      batch_id: Number(form.batch_id),
      semester_number: Number(form.semester_number),
    };
    try {
      if (editing !== null) await api.patch(`/api/v1/academic/module-offerings/${editing}`, payload);
      else await api.post("/api/v1/academic/module-offerings", payload);
      setForm(blank);
      setEdit(null);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save module offering.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row: any) {
    setTogglingId(row.id);
    setError("");
    try {
      await api.patch(`/api/v1/academic/module-offerings/${row.id}/activation?is_active=${!row.is_active}`);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to change offering status.");
    } finally {
      setTogglingId(null);
    }
  }

  function selectForEdit(row: any) {
    setError("");
    setEdit(row.id);
    setForm({
      academic_module_id: String(row.academic_module_id),
      intake_id: String(row.intake_id),
      batch_id: String(row.batch_id),
      semester_number: String(row.semester_number),
      is_active: row.is_active,
    });
  }

  const offeringFields = (autoFocusFirst = false) => <>
    {["academic_module_id", "intake_id", "batch_id"].map((key, index) => {
      const label = key === "academic_module_id" ? "Module" : key === "intake_id" ? "Intake" : "Batch";
      const kind = key === "academic_module_id" ? "modules" : key === "intake_id" ? "intakes" : "batches";
      const text = kind === "modules" ? "code" : kind === "intakes" ? "code" : "name";
      return <label key={key}>
        <span className="field-label">{label}</span>
        <select autoFocus={autoFocusFirst && index === 0} className="w-full" required value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })}>
          <option value="">Select {label.toLowerCase()}</option>
          {(data[kind] || []).map((item) => <option key={item.id} value={item.id}>{item[text]}{kind === "modules" ? ` — ${item.title}` : ""}</option>)}
        </select>
      </label>;
    })}

    <label>
      <span className="field-label">Semester</span>
      <input className="w-full" required type="number" min="1" value={form.semester_number} onChange={(event) => setForm({ ...form, semester_number: event.target.value })} />
    </label>

    <section className="rounded-lg border border-slate-700 bg-slate-950/70 p-3 md:col-span-2" aria-label="Inherited sections">
      <p className="text-sm font-medium text-slate-100">Inherited sections</p>
      <p className="mt-1 text-sm text-slate-400">This module will be available to every matching section now and to matching sections added later.</p>
      {cohortSections.length ? <div className="mt-3 flex flex-wrap gap-2">{cohortSections.map((section) => <Badge key={section.id} tone="neutral">{section.name}</Badge>)}</div> : <p className="mt-3 text-sm text-amber-300">No matching section exists yet. Future matching sections will inherit this offering.</p>}
    </section>

    <label className="flex items-center gap-2 self-end">
      <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
      <span className="text-sm font-medium">Active offering</span>
    </label>
  </>;

  return <div className="max-w-7xl">
    <PageHeader title="Module offerings" description="Offer a catalog module to one intake, batch, and semester. Every section in that cohort inherits it automatically." />

    <section className="panel p-5" aria-labelledby="create-module-offering-title">
      <div className="mb-5"><h2 id="create-module-offering-title" className="text-lg font-semibold">Add module offering</h2><p className="mt-1 text-sm text-slate-400">Create an offering for a cohort before building or importing its routine.</p></div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-3">
        {offeringFields()}
        <div className="md:col-span-3"><Button type="submit" loading={saving}>Create offering</Button></div>
      </form>
    </section>

    {error && edit === null && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}

    <div className="mt-7">
      {loading ? <LoadingState label="Loading module offerings…" /> : !rows.length ? <EmptyState title="No module offerings yet" description="Create an offering once for the cohort, then select it automatically while building or importing routines." /> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Module</th><th>Intake</th><th>Batch</th><th>Semester</th><th>Inherited sections</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.id}>
              <td className="font-medium text-slate-100">{row.module_code} — {row.module_title}</td>
              <td>{row.intake_code}</td><td>{row.batch_name}</td><td>{row.semester_number}</td>
              <td>{row.section_names.length ? <span>{row.section_names.join(" + ")} <span className="text-slate-500">({row.section_names.length} total)</span></span> : <span className="text-slate-500">Awaiting sections</span>}</td>
              <td><Badge tone={row.is_active ? "success" : "neutral"}>{row.is_active ? "Active" : "Inactive"}</Badge></td>
              <td><div className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => selectForEdit(row)}>Edit</Button><Button type="button" size="sm" variant="outline" loading={togglingId === row.id} disabled={togglingId !== null} onClick={() => void toggle(row)}>{row.is_active ? "Deactivate" : "Activate"}</Button></div></td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </div>

    {edit !== null && <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-module-offering-title">
      <button type="button" aria-label="Close edit dialog" className="absolute inset-0 bg-black/70" onClick={closeEdit} disabled={saving} />
      <section className="panel relative w-full max-w-3xl p-6">
        <div className="mb-5"><h2 id="edit-module-offering-title" className="text-xl font-semibold">Edit module offering</h2><p className="mt-1 text-sm text-slate-400">Update the cohort details and offering status, then save your changes.</p></div>
        {error && <p className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">{error}</p>}
        <form onSubmit={submit} className="grid gap-4 md:grid-cols-3">
          {offeringFields(true)}
          <div className="flex justify-end gap-2 md:col-span-3"><Button type="button" variant="ghost" onClick={closeEdit} disabled={saving}>Cancel</Button><Button type="submit" loading={saving}>Save changes</Button></div>
        </form>
      </section>
    </div>}
  </div>;
}
