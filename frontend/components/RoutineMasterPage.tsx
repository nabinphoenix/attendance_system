"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

export type Field = {
  key: string;
  label: string;
  type?: "text" | "number" | "date" | "time";
  optionsEndpoint?: string;
};

type MasterRecord = Record<string, unknown> & { id: number };

export default function RoutineMasterPage({
  title,
  endpoint,
  fields,
}: {
  title: string;
  endpoint: string;
  fields: Field[];
}) {
  const blank = () => Object.fromEntries(fields.map((field) => [field.key, ""]));
  const [rows, setRows] = useState<MasterRecord[]>([]);
  const [form, setForm] = useState<Record<string, string>>(blank());
  const [options, setOptions] = useState<Record<string, MasterRecord[]>>({});
  const [edit, setEdit] = useState<MasterRecord | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const optionEndpoints = useMemo(
    () => [...new Set(fields.map((field) => field.optionsEndpoint).filter(Boolean) as string[])],
    [fields],
  );

  async function load() {
    setLoading(true);
    setError("");
    try {
      const responses = await Promise.all([
        api.get(`/api/v1/academic/${endpoint}`),
        ...optionEndpoints.map((path) => api.get(path)),
      ]);
      setRows(responses[0].data);
      setOptions(Object.fromEntries(optionEndpoints.map((path, index) => [path, responses[index + 1].data])));
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load records.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [endpoint]);

  const payload = () => Object.fromEntries(
    fields.map((field) => [
      field.key,
      field.type === "number" || field.optionsEndpoint ? Number(form[field.key]) : form[field.key],
    ]),
  );

  function closeEdit() {
    setEdit(null);
    setForm(blank());
  }

  function startEdit(row: MasterRecord) {
    setError("");
    setEdit(row);
    setForm(Object.fromEntries(fields.map((field) => [field.key, String(row[field.key] ?? "")])));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const editing = edit;
    setSaving(true);
    setError("");
    try {
      if (editing) {
        await api.patch(`/api/v1/academic/${endpoint}/${editing.id}`, payload());
      } else {
        await api.post(`/api/v1/academic/${endpoint}`, payload());
      }
      setForm(blank());
      setEdit(null);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save this record.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (deleteId == null) return;
    try {
      await api.delete(`/api/v1/academic/${endpoint}/${deleteId}`);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to delete this record.");
    } finally {
      setDeleteId(null);
    }
  }

  const display = (row: MasterRecord, field: Field) => {
    if (!field.optionsEndpoint) return String(row[field.key] ?? "—");
    const match = options[field.optionsEndpoint]?.find((entry) => entry.id === row[field.key]);
    return String(match?.name ?? match?.code ?? "Not assigned");
  };

  const formFields = (autoFocusFirst = false) => fields.map((field, index) => (
    <label key={field.key}>
      <span className="field-label">{field.label}</span>
      {field.optionsEndpoint ? (
        <select
          autoFocus={autoFocusFirst && index === 0}
          className="w-full"
          required
          value={form[field.key]}
          onChange={(event) => setForm({ ...form, [field.key]: event.target.value })}
        >
          <option value="">Select {field.label.toLowerCase()}</option>
          {(options[field.optionsEndpoint] || []).map((entry) => (
            <option key={entry.id} value={entry.id}>{String(entry.name ?? entry.code)}</option>
          ))}
        </select>
      ) : (
        <input
          autoFocus={autoFocusFirst && index === 0}
          className="w-full"
          required
          type={field.type ?? "text"}
          value={form[field.key]}
          onChange={(event) => setForm({ ...form, [field.key]: event.target.value })}
        />
      )}
    </label>
  ));

  return <div className="max-w-6xl">
    <PageHeader title={title} description={`Manage ${title.toLowerCase()} used by the routine and attendance workflows.`} />

    <section className="panel p-5" aria-labelledby={`create-${endpoint}-title`}>
      <div className="mb-5">
        <h2 id={`create-${endpoint}-title`} className="text-lg font-semibold">Add {title.slice(0, -1)}</h2>
        <p className="mt-1 text-sm text-slate-400">Create a new record for this academic setup.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-3">
        {formFields()}
        <div className="flex items-end gap-2">
          <Button type="submit" loading={saving}>Create</Button>
        </div>
      </form>
    </section>

    {error && !edit && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}

    <div className="mt-7">
      {loading ? <LoadingState label={`Loading ${title.toLowerCase()}…`} /> : !rows.length ? (
        <EmptyState title={`No ${title.toLowerCase()} yet`} description="Create the first record using the form above." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {fields.map((field) => <th key={field.key}>{field.label}</th>)}
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {fields.map((field) => <td key={field.key}>{display(row, field)}</td>)}
                  <td>
                    <div className="flex justify-end gap-2">
                      <Button type="button" size="sm" variant="ghost" onClick={() => startEdit(row)}>Edit</Button>
                      <Button type="button" size="sm" variant="danger" onClick={() => setDeleteId(row.id)}>Delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>

    {edit && <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-record-title">
      <button type="button" aria-label="Close edit dialog" className="absolute inset-0 bg-black/70" onClick={closeEdit} disabled={saving} />
      <section className="panel relative w-full max-w-2xl p-6">
        <div className="mb-5">
          <h2 id="edit-record-title" className="text-xl font-semibold">Edit {title.slice(0, -1)}</h2>
          <p className="mt-1 text-sm text-slate-400">Update the selected record, then save your changes.</p>
        </div>
        {error && <p className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">{error}</p>}
        <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
          {formFields(true)}
          <div className="flex justify-end gap-2 md:col-span-2">
            <Button type="button" variant="ghost" onClick={closeEdit} disabled={saving}>Cancel</Button>
            <Button type="submit" loading={saving}>Save changes</Button>
          </div>
        </form>
      </section>
    </div>}

    <ConfirmDialog open={deleteId != null} title="Delete this record?" description="This action can only succeed when no related records depend on it." confirmLabel="Delete" tone="danger" onClose={() => setDeleteId(null)} onConfirm={remove} />
  </div>;
}
