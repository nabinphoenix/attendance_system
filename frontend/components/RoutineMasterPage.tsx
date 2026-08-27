"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

export type Field = {key:string;label:string;type?:"text"|"number"|"date"|"time";optionsEndpoint?:string};

export default function RoutineMasterPage({title,endpoint,fields}:{title:string;endpoint:string;fields:Field[]}) {
  const blank = () => Object.fromEntries(fields.map((field) => [field.key,""]));
  const [rows,setRows] = useState<any[]>([]);
  const [form,setForm] = useState<Record<string,string>>(blank());
  const [options,setOptions] = useState<Record<string,any[]>>({});
  const [edit,setEdit] = useState<any>(null);
  const [deleteId,setDeleteId] = useState<number|null>(null);
  const [error,setError] = useState("");
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const optionEndpoints = useMemo(() => [...new Set(fields.map((field) => field.optionsEndpoint).filter(Boolean) as string[])],[fields]);

  async function load() {
    setLoading(true); setError("");
    try { const responses = await Promise.all([api.get(`/api/v1/academic/${endpoint}`),...optionEndpoints.map((path) => api.get(path))]); setRows(responses[0].data); setOptions(Object.fromEntries(optionEndpoints.map((path,index) => [path,responses[index+1].data]))); }
    catch (requestError:any) { setError(requestError.response?.data?.detail ?? "Unable to load records."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [endpoint]);

  const payload = () => Object.fromEntries(fields.map((field) => [field.key,field.type === "number" || field.optionsEndpoint ? Number(form[field.key]) : form[field.key]]));
  async function submit(event:FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { if (edit) await api.patch(`/api/v1/academic/${endpoint}/${edit.id}`,payload()); else await api.post(`/api/v1/academic/${endpoint}`,payload()); setForm(blank()); setEdit(null); await load(); } catch (requestError:any) { setError(requestError.response?.data?.detail ?? "Unable to save this record."); } finally { setSaving(false); } }
  async function remove() { if (deleteId == null) return; try { await api.delete(`/api/v1/academic/${endpoint}/${deleteId}`); await load(); } catch (requestError:any) { setError(requestError.response?.data?.detail ?? "Unable to delete this record."); } finally { setDeleteId(null); } }
  const display = (row:any,field:Field) => { if (!field.optionsEndpoint) return String(row[field.key] ?? "—"); const match = options[field.optionsEndpoint]?.find((entry) => entry.id === row[field.key]); return match?.name ?? match?.code ?? "Not assigned"; };

  return <div className="max-w-6xl">
    <PageHeader title={title} description={`Manage ${title.toLowerCase()} used by the routine and attendance workflows.`} />
    <form onSubmit={submit} className="grid gap-4 panel p-5 md:grid-cols-3">{fields.map((field) => <label key={field.key}><span className="field-label">{field.label}</span>{field.optionsEndpoint ? <select className="w-full" required value={form[field.key]} onChange={(event) => setForm({...form,[field.key]:event.target.value})}><option value="">Select {field.label.toLowerCase()}</option>{(options[field.optionsEndpoint] || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name ?? entry.code}</option>)}</select> : <input className="w-full" required type={field.type ?? "text"} value={form[field.key]} onChange={(event) => setForm({...form,[field.key]:event.target.value})} />}</label>)}<div className="flex items-end gap-2"><Button loading={saving}>{edit ? "Save changes" : "Create"}</Button>{edit && <Button type="button" variant="ghost" onClick={() => { setEdit(null); setForm(blank()); }}>Cancel</Button>}</div></form>
    {error && <div className="mt-4"><ErrorState title="Unable to complete this action" description={error} onRetry={load} /></div>}
    <div className="mt-7">{loading ? <LoadingState label={`Loading ${title.toLowerCase()}…`} /> : !rows.length ? <EmptyState title={`No ${title.toLowerCase()} yet`} description="Create the first record using the form above." /> : <div className="table-wrap"><table><thead><tr>{fields.map((field) => <th key={field.key}>{field.label}</th>)}<th><span className="sr-only">Actions</span></th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>{fields.map((field) => <td key={field.key}>{display(row,field)}</td>)}<td><div className="flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => { setEdit(row); setForm(Object.fromEntries(fields.map((field) => [field.key,String(row[field.key] ?? "")]))); }}>Edit</Button><Button size="sm" variant="danger" onClick={() => setDeleteId(row.id)}>Delete</Button></div></td></tr>)}</tbody></table></div>}</div>
    <ConfirmDialog open={deleteId != null} title="Delete this record?" description="This action can only succeed when no related records depend on it." confirmLabel="Delete" tone="danger" onClose={() => setDeleteId(null)} onConfirm={remove} />
  </div>;
}
