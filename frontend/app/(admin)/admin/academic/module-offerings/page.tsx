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
    load();
  }, []);

  const cohortSections = useMemo(
    () =>
      (data.sections || []).filter(
        (section) =>
          (!form.batch_id || section.batch_id === Number(form.batch_id)) &&
          (!form.intake_id || section.intake_id === null || section.intake_id === Number(form.intake_id)) &&
          (!form.semester_number || section.semester_number === null || section.semester_number === Number(form.semester_number)),
      ),
    [data.sections, form.batch_id, form.intake_id, form.semester_number],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...form,
      academic_module_id: Number(form.academic_module_id),
      intake_id: Number(form.intake_id),
      batch_id: Number(form.batch_id),
      semester_number: Number(form.semester_number),
    };
    try {
      if (edit) await api.patch(`/api/v1/academic/module-offerings/${edit}`, payload);
      else await api.post("/api/v1/academic/module-offerings", payload);
      setForm(blank);
      setEdit(null);
      setError("");
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save module offering.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row: any) {
    try {
      await api.patch(`/api/v1/academic/module-offerings/${row.id}/activation?is_active=${!row.is_active}`);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to change offering status.");
    }
  }

  function selectForEdit(row: any) {
    setEdit(row.id);
    setForm({
      academic_module_id: String(row.academic_module_id),
      intake_id: String(row.intake_id),
      batch_id: String(row.batch_id),
      semester_number: String(row.semester_number),
      is_active: row.is_active,
    });
  }

  return (
    <div className="max-w-7xl">
      <PageHeader
        title="Module offerings"
        description="Offer a catalog module to one intake, batch, and semester. Every section in that cohort inherits it automatically."
      />

      <form onSubmit={submit} className="grid gap-4 panel p-5 md:grid-cols-3">
        {[["academic_module_id", "Module", "modules", "code"], ["intake_id", "Intake", "intakes", "code"], ["batch_id", "Batch", "batches", "name"]].map(([key, title, kind, text]) => (
          <label key={key}>
            <span className="field-label">{title}</span>
            <select className="w-full" required value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })}>
              <option value="">Select {title.toLowerCase()}</option>
              {(data[kind] || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item[text]}{kind === "modules" ? ` — ${item.title}` : ""}
                </option>
              ))}
            </select>
          </label>
        ))}

        <label>
          <span className="field-label">Semester</span>
          <input className="w-full" required type="number" min="1" value={form.semester_number} onChange={(event) => setForm({ ...form, semester_number: event.target.value })} />
        </label>

        <section className="rounded-lg border border-slate-700 bg-slate-950/70 p-3 md:col-span-2" aria-label="Inherited sections">
          <p className="text-sm font-medium text-slate-100">Inherited sections</p>
          <p className="mt-1 text-sm text-slate-400">There is no section selection here. This module will be available to every matching section now and to any section added later.</p>
          {cohortSections.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {cohortSections.map((section) => <Badge key={section.id} tone="neutral">{section.name}</Badge>)}
            </div>
          ) : (
            <p className="mt-3 text-sm text-amber-300">No matching section exists yet. You can still create the offering; future matching sections will inherit it.</p>
          )}
        </section>

        <label className="flex items-center gap-2 self-end">
          <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
          <span className="text-sm font-medium">Active offering</span>
        </label>

        <div className="flex gap-2 md:col-span-3">
          <Button loading={saving}>{edit ? "Save changes" : "Create offering"}</Button>
          {edit && <Button type="button" variant="ghost" onClick={() => { setEdit(null); setForm(blank); }}>Cancel</Button>}
        </div>
      </form>

      {error && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}

      <div className="mt-7">
        {loading ? <LoadingState label="Loading module offerings…" /> : !rows.length ? (
          <EmptyState title="No module offerings yet" description="Create an offering once for the cohort, then select it automatically while building or importing routines." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Module</th><th>Intake</th><th>Batch</th><th>Semester</th><th>Inherited sections</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="font-medium text-slate-100">{row.module_code} — {row.module_title}</td>
                    <td>{row.intake_code}</td>
                    <td>{row.batch_name}</td>
                    <td>{row.semester_number}</td>
                    <td>{row.section_names.length ? <span>{row.section_names.join(" + ")} <span className="text-slate-500">({row.section_names.length} total)</span></span> : <span className="text-slate-500">Awaiting sections</span>}</td>
                    <td><Badge tone={row.is_active ? "success" : "neutral"}>{row.is_active ? "Active" : "Inactive"}</Badge></td>
                    <td>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={() => selectForEdit(row)}>Edit</Button>
                        <Button size="sm" variant="outline" onClick={() => toggle(row)}>{row.is_active ? "Deactivate" : "Activate"}</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
