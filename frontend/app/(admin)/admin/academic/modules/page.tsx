"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

const blank = { code: "", title: "", credits: "", semester_number: "" };

export default function Page() {
  const [modules, setModules] = useState<any[]>([]);
  const [offerings, setOfferings] = useState<any[]>([]);
  const [form, setForm] = useState(blank);
  const [query, setQuery] = useState("");
  const [edit, setEdit] = useState<number | null>(null);
  const [deleteRow, setDeleteRow] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [moduleResponse, offeringResponse] = await Promise.all([
        api.get("/api/v1/academic/modules"),
        api.get("/api/v1/academic/module-offerings"),
      ]);
      setModules(moduleResponse.data);
      setOfferings(offeringResponse.data);
      setError("");
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load the BSc.IT course catalog.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return modules.filter((item) => !needle || item.code.toLowerCase().includes(needle) || item.title.toLowerCase().includes(needle));
  }, [modules, query]);

  function reset() {
    setForm(blank);
    setEdit(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload: Record<string, unknown> = {
      code: form.code.trim(),
      title: form.title.trim(),
      credits: Number(form.credits),
    };
    if (form.semester_number.trim()) payload.semester_number = Number(form.semester_number);
    try {
      if (edit === null) await api.post("/api/v1/academic/modules", payload);
      else await api.patch(`/api/v1/academic/modules/${edit}`, payload);
      reset();
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save the course.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!deleteRow) return;
    try {
      await api.delete(`/api/v1/academic/modules/${deleteRow.id}`);
      setDeleteRow(null);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to delete the course.");
      setDeleteRow(null);
    }
  }

  return <div className="max-w-7xl">
    <PageHeader title="BSc.IT course catalog" description="Reusable course records are kept separate from the batch-semester offerings that use them." />
    <section className="panel p-5" aria-labelledby="catalog-form-title">
      <div className="mb-5"><h2 id="catalog-form-title" className="text-lg font-semibold">{edit === null ? "Add course" : "Edit course"}</h2><p className="mt-1 text-sm text-slate-400">Semester metadata is optional catalog information; assign the actual semester through a module offering.</p></div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-4">
        <label><span className="field-label">Course code</span><input className="w-full" required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></label>
        <label className="md:col-span-2"><span className="field-label">Course name</span><input className="w-full" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <label><span className="field-label">Credits</span><input className="w-full" required type="number" min="0" value={form.credits} onChange={(event) => setForm({ ...form, credits: event.target.value })} /></label>
        <label><span className="field-label">Legacy semester metadata (optional)</span><input className="w-full" type="number" min="1" max="6" value={form.semester_number} onChange={(event) => setForm({ ...form, semester_number: event.target.value })} /></label>
        <div className="flex items-end gap-3 md:col-span-3"><Button type="submit" loading={saving}>{edit === null ? "Add course" : "Save changes"}</Button>{edit !== null && <Button type="button" variant="ghost" onClick={reset} disabled={saving}>Cancel</Button>}</div>
      </form>
    </section>
    {error && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}
    <section className="mt-7" aria-labelledby="catalog-list-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 id="catalog-list-title" className="text-lg font-semibold">Available courses</h2><p className="text-sm text-slate-400">{filtered.length} matching course{filtered.length === 1 ? "" : "s"}</p></div><input aria-label="Search course catalog" placeholder="Search code or name" className="w-full md:w-80" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      {loading ? <LoadingState label="Loading course catalog" /> : <div className="table-wrap" role="region" aria-label="Scrollable records" tabIndex={0}><table><thead><tr><th>Course code</th><th>Course name</th><th>Credits</th><th>Catalog semester</th><th>Assignment status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
        {filtered.map((item) => { const count = offerings.filter((offering) => offering.academic_module_id === item.id).length; return <tr key={item.id}><td className="font-medium text-slate-100">{item.code}</td><td>{item.title}</td><td>{item.credits}</td><td>{item.semester_number ?? <span className="text-slate-500">Not fixed</span>}</td><td><Badge tone={count ? "success" : "neutral"}>{count ? `${count} offering${count === 1 ? "" : "s"}` : "Catalog only"}</Badge></td><td><div className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => { setEdit(item.id); setForm({ code: item.code, title: item.title, credits: String(item.credits), semester_number: item.semester_number == null ? "" : String(item.semester_number) }); }}>Edit</Button><Button type="button" size="sm" variant="danger" onClick={() => setDeleteRow(item)}>Delete</Button></div></td></tr>; })}
        {!filtered.length && <tr><td colSpan={6} className="p-0"><EmptyState title="No matching courses" description="Add the course to the catalog or change the search term." /></td></tr>}
      </tbody></table></div>}
    </section>
    <ConfirmDialog open={deleteRow !== null} title="Delete this catalog course?" description="A course with linked offerings or routines cannot be deleted." confirmLabel="Delete course" tone="danger" onClose={() => setDeleteRow(null)} onConfirm={remove} />
  </div>;
}
