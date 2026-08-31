"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type ImportRow = { row_number: number; status: string; message: string; data: Record<string, unknown> };
type Job = { id: number; file_name: string; upload_type: string; total_rows: number; success_count: number; failed_count: number; errors: { row_number: number; error_message: string }[]; results?: ImportRow[] };

const PAGE_SIZE = 5;

function formatRowData(data: Record<string, unknown>) {
  const entries = Object.entries(data);
  return entries.length ? entries.map(([key, value]) => `${key}: ${value == null ? "" : String(value)}`).join(" - ") : "No row values recorded";
}

export default function Page() {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("students");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [result, setResult] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [historyPage, setHistoryPage] = useState(1);
  const [detailPage, setDetailPage] = useState(1);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const response = await api.get<Job[]>("/api/v1/imports");
      setJobs(response.data);
      setHistoryPage((page) => Math.min(page, Math.max(1, Math.ceil(response.data.length / PAGE_SIZE))));
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load import history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) { setError("Choose a CSV or XLSX file to continue."); return; }
    setUploading(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const uploaded = (await api.post<Job>(`/api/v1/imports/${kind}`, body)).data;
      setResult(uploaded); setDetailPage(1);
      setFile(null); if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "The file could not be imported.");
    } finally {
      setUploading(false);
    }
  }

  async function showDetails(id: number) {
    setDetailsLoading(true); setError("");
    try {
      const response = await api.get<Job>(`/api/v1/imports/${id}`);
      setResult(response.data); setDetailPage(1);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load import details.");
    } finally {
      setDetailsLoading(false);
    }
  }

  const historyPageCount = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));
  const visibleJobs = jobs.slice((historyPage - 1) * PAGE_SIZE, historyPage * PAGE_SIZE);
  const detailRows: ImportRow[] = result?.results?.length
    ? result.results
    : result?.errors.map((item) => ({ row_number: item.row_number, status: "failed", message: item.error_message, data: {} })) ?? [];
  const detailPageCount = Math.max(1, Math.ceil(detailRows.length / PAGE_SIZE));
  const visibleDetailRows = detailRows.slice((detailPage - 1) * PAGE_SIZE, detailPage * PAGE_SIZE);

  const hint = kind === "students"
    ? "Required columns: name, email, batch_name, section_name, phone. Each successful student import automatically queues a secure account-setup email."
    : "Routine files accept MON-SUN or full day names. For a preview before publishing, use the Routine page import panel.";

  return <div className="max-w-6xl">
    <PageHeader title="Bulk imports" description="Bring student or routine data into AntimBench from a CSV or Excel workbook." />
    <form onSubmit={submit} className="panel p-5 sm:p-6">
      <label className="field-label" htmlFor="import-kind">Import type</label>
      <select id="import-kind" className="w-full sm:max-w-xs" value={kind} onChange={(event) => { setKind(event.target.value); setFile(null); }}><option value="students">Students</option><option value="routines">Routines</option></select>
      <p className="helper-text">{hint}</p>
      <label className="mt-5 flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-600 bg-slate-950/50 px-6 py-8 text-center transition hover:border-emerald-500 hover:bg-emerald-500/5 focus-within:ring-2 focus-within:ring-emerald-400">
        <span className="grid h-11 w-11 place-items-center rounded-full bg-slate-800 text-xl text-emerald-300" aria-hidden="true">&#8593;</span>
        <span className="mt-3 font-semibold text-slate-100">{file ? file.name : "Drop a CSV/XLSX file here"}</span>
        <span className="mt-1 text-sm text-slate-400">{file ? `${Math.ceil(file.size / 1024)} KB selected` : "or choose a file from your device"}</span>
        <input ref={fileInput} className="sr-only" type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </label>
      <div className="mt-5 flex justify-end"><Button loading={uploading} disabled={!file}>{uploading ? "Importing..." : "Import file"}</Button></div>
    </form>

    {error && <div className="mt-5"><ErrorState title="Import unavailable" description={error} onRetry={load} /></div>}
    {result && <section className="mt-6 panel p-5 sm:p-6" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-slate-400">Import details</p><h2 className="text-lg font-semibold">{result.file_name}</h2></div><div className="flex items-center gap-2"><Badge tone={result.failed_count ? "warning" : "success"}>{result.failed_count ? "Completed with errors" : "Completed"}</Badge><Button variant="ghost" size="sm" onClick={() => setResult(null)}>Close</Button></div></div>
      <div className="mt-5 grid grid-cols-3 gap-3">{[["Rows", result.total_rows, "text-slate-100"], ["Succeeded", result.success_count, "text-emerald-300"], ["Failed", result.failed_count, "text-red-300"]].map(([label, value, tone]) => <div key={String(label)} className="rounded-lg bg-slate-950/60 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p></div>)}</div>
      {result.upload_type === "students" && result.success_count > 0 && <p className="mt-5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">Secure account-setup emails were queued for {result.success_count} newly created student account{result.success_count === 1 ? "" : "s"}. Students choose their own password before signing in.</p>}
      <div className="mt-5 flex items-center justify-between gap-3"><div><h3 className="font-semibold">Row outcomes</h3><p className="mt-1 text-sm text-slate-400">Every source row is listed with its import status and result.</p></div>{detailsLoading && <span className="text-sm text-slate-400">Loading details...</span>}</div>
      {detailsLoading ? <div className="mt-4"><LoadingState label="Loading import details..." /></div> : !detailRows.length ? <p className="mt-4 rounded-lg border border-slate-700 p-4 text-sm text-slate-400">No row-level details were recorded for this import.</p> : <>
        <div className="mt-4 table-wrap overflow-x-auto"><table><thead><tr><th>Row</th><th>Status</th><th>Imported values</th><th>Outcome</th></tr></thead><tbody>{visibleDetailRows.map((row) => <tr key={`${result.id}-${row.row_number}-${row.status}`}><td>{row.row_number}</td><td><Badge tone={row.status === "success" ? "success" : "danger"}>{row.status === "success" ? "Success" : "Failed"}</Badge></td><td className="max-w-md text-sm text-slate-300">{formatRowData(row.data)}</td><td className={row.status === "success" ? "text-emerald-300" : "text-red-300"}>{row.message}</td></tr>)}</tbody></table></div>
        {detailPageCount > 1 && <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-400">Showing {(detailPage - 1) * PAGE_SIZE + 1}-{Math.min(detailPage * PAGE_SIZE, detailRows.length)} of {detailRows.length} rows</p><div className="flex items-center gap-2"><Button variant="outline" size="sm" onClick={() => setDetailPage((page) => Math.max(1, page - 1))} disabled={detailPage === 1}>Previous</Button><span className="text-sm text-slate-400">Page {detailPage} of {detailPageCount}</span><Button variant="outline" size="sm" onClick={() => setDetailPage((page) => Math.min(detailPageCount, page + 1))} disabled={detailPage === detailPageCount}>Next</Button></div></div>}
      </>}
    </section>}

    <section className="mt-8"><h2 className="text-lg font-semibold">Import history</h2><p className="mt-1 text-sm text-slate-400">Review the outcome of recent uploads.</p>
      <div className="mt-4">{loading ? <LoadingState label="Loading import history..." /> : !jobs.length ? <EmptyState title="No imports yet" description="Your completed imports will be listed here." /> : <>
        <div className="table-wrap"><table><thead><tr><th>File</th><th>Type</th><th>Rows</th><th>Successful</th><th>Failed</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{visibleJobs.map((job) => <tr key={job.id}><td className="font-medium text-slate-100">{job.file_name}</td><td><span className="capitalize">{job.upload_type}</span></td><td>{job.total_rows}</td><td className="text-emerald-300">{job.success_count}</td><td className={job.failed_count ? "text-red-300" : "text-slate-400"}>{job.failed_count}</td><td className="text-right"><Button variant="ghost" size="sm" loading={detailsLoading} onClick={() => void showDetails(job.id)}>View details</Button></td></tr>)}</tbody></table></div>
        {historyPageCount > 1 && <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-400">Showing {(historyPage - 1) * PAGE_SIZE + 1}-{Math.min(historyPage * PAGE_SIZE, jobs.length)} of {jobs.length} imports</p><div className="flex items-center gap-2"><Button variant="outline" size="sm" onClick={() => setHistoryPage((page) => Math.max(1, page - 1))} disabled={historyPage === 1}>Previous</Button><span className="text-sm text-slate-400">Page {historyPage} of {historyPageCount}</span><Button variant="outline" size="sm" onClick={() => setHistoryPage((page) => Math.min(historyPageCount, page + 1))} disabled={historyPage === historyPageCount}>Next</Button></div></div>}
      </>}</div>
    </section>
  </div>;
}
