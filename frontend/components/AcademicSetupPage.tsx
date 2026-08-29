"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

type Row = Record<string, string | number>;
type Field = { name: string; label: string; type?: "text" | "email" | "password" | "number"; optionsEndpoint?: string };
type Column = { label: string; field: string; optionsEndpoint?: string };

export type AcademicSetupConfig = {
  title: string;
  singular: string;
  endpoint: string;
  fields: Field[];
  columns: Column[];
};

export default function AcademicSetupPage({ config }: { config: AcademicSetupConfig }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [options, setOptions] = useState<Record<string, Row[]>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [edit, setEdit] = useState<Row | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const size = 20;
  const endpoints = useMemo(
    () => [...new Set(config.fields.map((field) => field.optionsEndpoint).filter(Boolean) as string[])],
    [config.fields],
  );
  const columns = config.columns.filter((column) => column.field !== "id");

  const load = async (nextPage = page) => {
    setLoading(true);
    setError("");
    try {
      const [first, ...rest] = await Promise.all([
        api.get(`${config.endpoint}/page?page_number=${nextPage}&page_size=${size}`),
        ...endpoints.map((endpoint) => api.get(endpoint)),
      ]);
      setRows(first.data.items);
      setTotal(first.data.total);
      setPage(nextPage);
      setOptions(Object.fromEntries(endpoints.map((endpoint, index) => [endpoint, rest[index].data])));
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load records");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(1);
  }, [config.endpoint]);

  const body = (source: Record<string, string | number>) => Object.fromEntries(
    config.fields.flatMap((field) => {
      const value = String(source[field.name] ?? "").trim();
      return value ? [[field.name, field.optionsEndpoint || field.type === "number" ? Number(value) : value]] : [];
    }),
  );

  function closeEdit() {
    setEdit(null);
    setValues({});
  }

  function startEdit(row: Row) {
    setError("");
    setEdit(row);
    setValues(Object.fromEntries(config.fields.map((field) => [field.name, String(row[field.name] ?? "")])));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const payload = body(values);
    if (Object.keys(payload).length !== config.fields.length) {
      setError("Complete all required fields.");
      return;
    }
    const editing = edit;
    setSaving(true);
    setError("");
    try {
      if (editing) await api.patch(`${config.endpoint}/${editing.id}`, payload);
      else await api.post(config.endpoint, payload);
      setValues({});
      setEdit(null);
      await load(1);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save record");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (deleteId == null) return;
    try {
      await api.delete(`${config.endpoint}/${deleteId}`);
      await load(page);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to delete");
    } finally {
      setDeleteId(null);
    }
  }

  const display = (row: Row, column: Column) => {
    const match = column.optionsEndpoint ? options[column.optionsEndpoint]?.find((item) => item.id === row[column.field]) : null;
    return String(match ? match.name ?? match.code ?? "—" : row[column.field] ?? "—");
  };

  const fields = (autoFocusFirst = false) => config.fields.map((field, index) => (
    <label key={field.name}>
      <span className="field-label">{field.label}</span>
      {field.optionsEndpoint ? (
        <select
          autoFocus={autoFocusFirst && index === 0}
          required
          className="w-full"
          value={values[field.name] ?? ""}
          onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
        >
          <option value="">Select {field.label.toLowerCase()}</option>
          {(options[field.optionsEndpoint] || []).map((option) => (
            <option key={option.id} value={option.id}>{String(option.name ?? option.code ?? "")}</option>
          ))}
        </select>
      ) : (
        <input
          autoFocus={autoFocusFirst && index === 0}
          required
          type={field.type ?? "text"}
          className="w-full"
          value={values[field.name] ?? ""}
          autoComplete={field.type === "password" ? "new-password" : undefined}
          onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
        />
      )}
    </label>
  ));

  return <div className="max-w-6xl">
    <PageHeader title={config.title} description={`Manage ${config.title.toLowerCase()} used across AntimBench.`} />

    <section className="panel p-5" aria-labelledby={`create-${config.singular}-title`}>
      <div className="mb-5">
        <h2 id={`create-${config.singular}-title`} className="text-lg font-semibold">Add {config.singular}</h2>
        <p className="mt-1 text-sm text-slate-400">Create a new record for this academic setup.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        {fields()}
        <div className="flex items-end gap-3">
          <Button type="submit" loading={saving}>Create {config.singular.toLowerCase()}</Button>
        </div>
      </form>
    </section>

    {error && !edit && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={() => void load(page)} /></div>}

    <div className="mt-7">
      {loading ? <LoadingState label={`Loading ${config.title}`} /> : (
        <div className="table-wrap">
          <table>
            <thead><tr>{columns.map((column) => <th key={column.field}>{column.label}</th>)}<th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {rows.map((row) => <tr key={row.id}>
                {columns.map((column) => <td key={column.field}>{display(row, column)}</td>)}
                <td><div className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => startEdit(row)}>Edit</Button><Button type="button" size="sm" variant="danger" onClick={() => setDeleteId(Number(row.id))}>Delete</Button></div></td>
              </tr>)}
              {!rows.length && <tr><td colSpan={columns.length + 1} className="p-0"><EmptyState title={`No ${config.title.toLowerCase()} yet`} description={`Create the first ${config.singular.toLowerCase()} using the form above.`} /></td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>

    <div className="mt-4 flex items-center justify-between gap-3"><Button type="button" variant="outline" disabled={page === 1 || loading} onClick={() => void load(page - 1)}>Previous</Button><span className="text-sm text-slate-400">Page {page} of {Math.max(1, Math.ceil(total / size))}</span><Button type="button" variant="outline" disabled={page * size >= total || loading} onClick={() => void load(page + 1)}>Next</Button></div>

    {edit && <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-academic-record-title">
      <button type="button" aria-label="Close edit dialog" className="absolute inset-0 bg-black/70" onClick={closeEdit} disabled={saving} />
      <section className="panel relative w-full max-w-xl p-6">
        <div className="mb-5"><h2 id="edit-academic-record-title" className="text-xl font-semibold">Edit {config.singular}</h2><p className="mt-1 text-sm text-slate-400">Update the selected record, then save your changes.</p></div>
        {error && <p className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">{error}</p>}
        <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
          {fields(true)}
          <div className="flex justify-end gap-2 md:col-span-2"><Button type="button" variant="ghost" onClick={closeEdit} disabled={saving}>Cancel</Button><Button type="submit" loading={saving}>Save changes</Button></div>
        </form>
      </section>
    </div>}

    <ConfirmDialog open={deleteId != null} title={`Delete this ${config.singular.toLowerCase()}?`} description="This action can only succeed when no related records depend on it." confirmLabel="Delete" tone="danger" onClose={() => setDeleteId(null)} onConfirm={remove} />
  </div>;
}
