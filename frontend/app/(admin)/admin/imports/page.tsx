"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type Job = {id:number;file_name:string;upload_type:string;total_rows:number;success_count:number;failed_count:number;errors:{row_number:number;error_message:string}[]};

export default function Page() {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("students");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [result, setResult] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    try { setJobs((await api.get("/api/v1/imports")).data); }
    catch (requestError: any) { setError(requestError.response?.data?.detail ?? "Unable to load import history."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) { setError("Choose a CSV or XLSX file to continue."); return; }
    setUploading(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      setResult((await api.post(`/api/v1/imports/${kind}`, body)).data);
      setFile(null); if (fileInput.current) fileInput.current.value = ""; await load();
    } catch (requestError: any) { setError(requestError.response?.data?.detail ?? "The file could not be imported."); }
    finally { setUploading(false); }
  }

  const hint = kind === "students" ? "Required columns: name, email, batch_name, section_name, phone." : "Routine files accept MON–SUN or full day names. For a preview before publishing, use the Routine page import panel.";
  return <div className="max-w-6xl">
    <PageHeader title="Bulk imports" description="Bring student or routine data into AntimBench from a CSV or Excel workbook." />
    <form onSubmit={submit} className="panel p-5 sm:p-6">
      <label className="field-label" htmlFor="import-kind">Import type</label>
      <select id="import-kind" className="w-full sm:max-w-xs" value={kind} onChange={(event) => { setKind(event.target.value); setFile(null); }}><option value="students">Students</option><option value="routines">Routines</option></select>
      <p className="helper-text">{hint}</p>
      <label className="mt-5 flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-600 bg-slate-950/50 px-6 py-8 text-center transition hover:border-emerald-500 hover:bg-emerald-500/5 focus-within:ring-2 focus-within:ring-emerald-400">
        <span className="grid h-11 w-11 place-items-center rounded-full bg-slate-800 text-xl text-emerald-300" aria-hidden="true">↑</span>
        <span className="mt-3 font-semibold text-slate-100">{file ? file.name : "Drop a CSV/XLSX file here"}</span>
        <span className="mt-1 text-sm text-slate-400">{file ? `${Math.ceil(file.size / 1024)} KB selected` : "or choose a file from your device"}</span>
        <input ref={fileInput} className="sr-only" type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </label>
      <div className="mt-5 flex justify-end"><Button loading={uploading} disabled={!file}>{uploading ? "Importing…" : "Import file"}</Button></div>
    </form>

    {error && <div className="mt-5"><ErrorState title="Import unavailable" description={error} onRetry={load} /></div>}
    {result && <section className="mt-6 panel p-5 sm:p-6" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-slate-400">Latest import</p><h2 className="text-lg font-semibold">{result.file_name}</h2></div><Badge tone={result.failed_count ? "warning" : "success"}>{result.failed_count ? "Completed with errors" : "Completed"}</Badge></div>
      <div className="mt-5 grid grid-cols-3 gap-3">{[["Rows",result.total_rows,"text-slate-100"],["Succeeded",result.success_count,"text-emerald-300"],["Failed",result.failed_count,"text-red-300"]].map(([label,value,tone]) => <div key={String(label)} className="rounded-lg bg-slate-950/60 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p></div>)}</div>
      {!!result.errors.length && <div className="mt-5 table-wrap"><table><thead><tr><th>Row</th><th>What needs attention</th></tr></thead><tbody>{result.errors.map((item) => <tr key={item.row_number}><td>{item.row_number}</td><td className="text-red-300">{item.error_message}</td></tr>)}</tbody></table></div>}
    </section>}

    <section className="mt-8"><h2 className="text-lg font-semibold">Import history</h2><p className="mt-1 text-sm text-slate-400">Review the outcome of recent uploads.</p>
      <div className="mt-4">{loading ? <LoadingState label="Loading import history…" /> : !jobs.length ? <EmptyState title="No imports yet" description="Your completed imports will be listed here." /> : <div className="table-wrap"><table><thead><tr><th>File</th><th>Type</th><th>Rows</th><th>Successful</th><th>Failed</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td className="font-medium text-slate-100">{job.file_name}</td><td><span className="capitalize">{job.upload_type}</span></td><td>{job.total_rows}</td><td className="text-emerald-300">{job.success_count}</td><td className={job.failed_count ? "text-red-300" : "text-slate-400"}>{job.failed_count}</td><td className="text-right"><Button variant="ghost" size="sm" onClick={async () => setResult((await api.get(`/api/v1/imports/${job.id}`)).data)}>View details</Button></td></tr>)}</tbody></table></div>}</div>
    </section>
  </div>;
}
