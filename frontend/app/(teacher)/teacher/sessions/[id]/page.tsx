"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import api from "@/lib/api";
import QRDisplay from "@/components/QRDisplay";
import ProfileAvatar from "@/components/ProfileAvatar";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/States";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

type Row = { attendance_id: number | null; student_id: number; student_name: string; roll_number: string; status: string; check_in_time: string | null; distance_meters: number | null; allowed_radius_meters: number | null; location_accuracy_meters: number | null };
type ExceptionRow = { id: number; student_name: string; roll_number: string; section_name: string; reason: string; distance_meters: number | null; allowed_radius_meters: number | null; accuracy_meters: number | null; created_at: string; status: string };
type QRData = { token: string; expires_at: string; rotation_seconds: number; self_checkin_window_minutes: number; self_checkin_closes_at: string; module_title: string; section_names: string[]; room: string; start_time: string; end_time: string; geofence_radius_meters: number | null; teacher_location_accuracy_meters: number | null; classroom_code: string; challenge_id: number };
type DialogAction = { kind: "finalize" } | { kind: "exception"; item: ExceptionRow; decision: "confirm" | "reject" } | { kind: "status"; row: Row; status: string };
type RosterView = "grid" | "list";
type RosterFilter = "all" | "present" | "absent";

const correctionStatuses = ["present", "late", "absent", "leave", "bunk"];
const meters = (value: number | null) => value == null ? "-" : `${Math.round(value)}m`;
const rosterTone: Record<string, string> = {
  present: "border-emerald-400 bg-emerald-950/70 ring-1 ring-emerald-400/45", late: "border-emerald-400 bg-emerald-950/70 ring-1 ring-emerald-400/45",
  absent: "border-red-400 bg-red-950/65 ring-1 ring-red-400/40", rejected: "border-red-400 bg-red-950/65 ring-1 ring-red-400/40", bunk: "border-red-400 bg-red-950/65 ring-1 ring-red-400/40",
  leave: "border-amber-400 bg-amber-950/55 ring-1 ring-amber-400/35", pending_verification: "border-amber-400 bg-amber-950/55 ring-1 ring-amber-400/35",
  not_checked_in: "border-slate-600 bg-slate-900/80 ring-1 ring-slate-700/60",
};
const rosterToneFor = (status: string) => rosterTone[status] ?? rosterTone.not_checked_in;
const statusLabel = (status: string) => status.replaceAll("_", " ");
const isPresentStatus = (status: string) => status === "present" || status === "late";
const isAbsentStatus = (status: string) => status === "absent" || status === "rejected" || status === "bunk";
const timeLabel = (value: string | null) => {
  if (!value) return "No check-in";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "No check-in" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};
const durationLabel = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
const distanceLabel = (row: Row) => row.distance_meters == null ? "Location not recorded" : `${Math.round(row.distance_meters)}m from teacher${row.allowed_radius_meters == null ? "" : ` / ${Math.round(row.allowed_radius_meters)}m boundary`}`;

function GridIcon() { return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-2"><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></svg>; }
function ListIcon() { return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-2"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" strokeLinecap="round" /></svg>; }

export default function Page() {
  const { id } = useParams<{ id: string }>();
  const [qr, setQr] = useState<QRData | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionRow[]>([]);
  const [message, setMessage] = useState("");
  const [completed, setCompleted] = useState(false);
  const [checkInClosed, setCheckInClosed] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [checkInSecondsRemaining, setCheckInSecondsRemaining] = useState(0);
  const [dialog, setDialog] = useState<DialogAction | null>(null);
  const [rosterView, setRosterView] = useState<RosterView>("grid");
  const [rosterFilter, setRosterFilter] = useState<RosterFilter>("all");
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    const [qrResult, rosterResult, exceptionsResult] = await Promise.allSettled([
      api.get<QRData>(`/api/v1/sessions/${id}/qr`), api.get<Row[]>(`/api/v1/sessions/${id}/summary`), api.get<ExceptionRow[]>(`/api/v1/sessions/${id}/check-in-exceptions`),
    ]);
    if (qrResult.status === "fulfilled") { setQr(qrResult.value.data); setCompleted(false); setCheckInClosed(false); }
    else if (qrResult.reason?.response?.status === 409) {
      setQr(null);
      if (qrResult.reason?.response?.data?.detail === "SELF_CHECKIN_WINDOW_CLOSED") setCheckInClosed(true);
      else { setCompleted(true); setCheckInClosed(false); }
    }
    if (rosterResult.status === "fulfilled") setRows(rosterResult.value.data);
    if (exceptionsResult.status === "fulfilled") setExceptions(exceptionsResult.value.data);
  }, [id]);

  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 3000); return () => window.clearInterval(timer); }, [refresh]);
  useEffect(() => { const timer = window.setInterval(() => setCountdown(qr ? Math.max(0, Math.ceil((new Date(qr.expires_at).getTime() - Date.now()) / 1000)) : 0), 250); return () => window.clearInterval(timer); }, [qr]);
  useEffect(() => {
    const update = () => {
      const remaining = qr ? Math.max(0, Math.ceil((new Date(qr.self_checkin_closes_at).getTime() - Date.now()) / 1000)) : 0;
      setCheckInSecondsRemaining(remaining);
      if (qr && remaining === 0) { setCheckInClosed(true); setQr(null); }
    };
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [qr]);

  const counts = useMemo(() => ({
    total: rows.length,
    present: rows.filter((row) => isPresentStatus(row.status)).length,
    absent: rows.filter((row) => isAbsentStatus(row.status)).length,
    pending: rows.filter((row) => row.status === "pending_verification").length,
    remaining: rows.filter((row) => row.status === "not_checked_in").length,
  }), [rows]);
  const attendanceRate = counts.total ? Math.round((counts.present / counts.total) * 100) : 0;
  const visibleRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesFilter = rosterFilter === "all" || (rosterFilter === "present" ? isPresentStatus(row.status) : isAbsentStatus(row.status));
      const matchesSearch = !query || row.student_name.toLowerCase().includes(query) || row.roll_number.toLowerCase().includes(query);
      return matchesFilter && matchesSearch;
    });
  }, [rows, rosterFilter, search]);

  async function finalize() {
    try { await api.post(`/api/v1/sessions/${id}/finalize`); setMessage("Session finalized successfully."); setCompleted(true); await refresh(); }
    catch (error: any) { setMessage(error.response?.data?.detail ?? "Unable to finalize this session"); }
  }
  async function decide(item: ExceptionRow, decision: "confirm" | "reject", reason: string) {
    try { await api.patch(`/api/v1/sessions/${id}/check-in-exceptions/${item.id}`, { decision, reason }); setMessage(decision === "confirm" ? `${item.student_name} confirmed present.` : `${item.student_name}'s attempt was rejected.`); await refresh(); }
    catch (error: any) { setMessage(error.response?.data?.detail ?? "Unable to review this attempt"); }
  }
  async function change(row: Row, status: string, reason: string) { await api.put(`/api/v1/sessions/${id}/attendance/${row.student_id}`, { status, reason }); setMessage(`${row.student_name}'s attendance was updated.`); await refresh(); }
  async function regenerateChallenge() {
    try {
      const response = await api.post<QRData>(`/api/v1/sessions/${id}/challenge`);
      setQr(response.data);
      setMessage("A new QR and classroom code have been generated. The previous pair is no longer valid.");
      await refresh();
    } catch (error: any) { setMessage(error.response?.data?.detail ?? "Unable to generate a new classroom challenge."); }
  }
  async function confirmAction(reason: string) { if (!dialog) return; if (dialog.kind === "finalize") await finalize(); else if (dialog.kind === "exception") await decide(dialog.item, dialog.decision, reason); else await change(dialog.row, dialog.status, reason); }

  const dialogInfo = dialog?.kind === "finalize"
    ? { title: "Finalize attendance?", description: "Students who have not checked in will be finalized using the attendance rules. Resolve pending verifications first.", label: "Finalize session", tone: "danger" as const, reason: false }
    : dialog?.kind === "exception"
      ? { title: dialog.decision === "confirm" ? `Confirm ${dialog.item.student_name} present?` : `Reject ${dialog.item.student_name}'s attempt?`, description: "This decision is recorded in the attendance audit trail.", label: dialog.decision === "confirm" ? "Confirm present" : "Reject attempt", tone: dialog.decision === "confirm" ? "primary" as const : "danger" as const, reason: true }
      : dialog?.kind === "status"
        ? { title: `Change ${dialog.row.student_name} to ${statusLabel(dialog.status)}?`, description: "Add a reason for this manual attendance correction.", label: "Save correction", tone: "primary" as const, reason: true }
        : null;

  const correctionSelect = (row: Row) => <select aria-label={`Correct attendance for ${row.student_name}`} value={row.status} onChange={(event) => setDialog({ kind: "status", row, status: event.target.value })}>
    {!correctionStatuses.includes(row.status) && <option value={row.status}>{statusLabel(row.status)}</option>}
    {correctionStatuses.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
  </select>;

  return <div>
    <PageHeader title={completed ? "Session summary" : checkInClosed ? "Self check-in closed" : "Live attendance session"} description={qr ? `${qr.module_title} - ${qr.section_names.join(" + ")}` : checkInClosed ? "The check-in deadline has passed. Manual attendance and finalization remain available." : "Attendance and location verification"} action={completed ? <Link href="/teacher/sessions" className="inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-400 bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:border-emerald-300 hover:bg-emerald-300">Start another session</Link> : <Button variant="outline" onClick={() => setDialog({ kind: "finalize" })}>Finalize session</Button>} />
    {message && <p role="status" className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</p>}
    {checkInClosed && <section className="my-6 rounded-xl border border-amber-500/35 bg-amber-500/10 p-5"><Badge tone="warning">Self check-in closed</Badge><h2 className="mt-3 text-xl font-semibold">QR attendance is no longer available</h2><p className="mt-2 text-sm text-slate-300">The configured check-in window has ended, so the QR and classroom code are hidden. You can still record manual attendance, review exceptions, or finalize this session.</p></section>}
    {qr && <section className="panel my-6 grid items-center gap-8 p-5 sm:p-7 lg:grid-cols-[minmax(300px,420px)_1fr]">
      <div><QRDisplay value={qr.token} /><div className="mx-auto mt-3 max-w-[380px]"><div className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-emerald-400 transition-[width]" style={{ width: `${Math.max(0, Math.min(100, (countdown / qr.rotation_seconds) * 100))}%` }} /></div><p className="mt-2 text-center text-sm font-medium text-emerald-300">QR and code change in {countdown} seconds</p><p className="mt-1 text-center text-sm font-semibold text-amber-300">Self check-in closes in {durationLabel(checkInSecondsRemaining)}</p></div></div>
      <div><Badge tone="success">Session active</Badge><h2 className="mt-4 text-2xl font-semibold sm:text-3xl">{qr.module_title}</h2><p className="mt-2 text-lg text-slate-300">{qr.section_names.join(" + ")}</p><div className="mt-6 rounded-2xl border border-emerald-400/40 bg-emerald-400/10 p-5 text-center"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">Announce this class code</p><p className="mt-2 font-mono text-5xl font-bold tracking-[0.3em] text-emerald-100">{qr.classroom_code}</p><p className="mt-3 text-sm text-slate-300">Students must enter this code after scanning the QR.</p><Button className="mt-4" variant="outline" onClick={() => void regenerateChallenge()}>Generate New Challenge</Button></div><dl className="mt-6 grid gap-4 sm:grid-cols-3"><div><dt className="text-xs uppercase tracking-wider text-slate-500">Time</dt><dd className="mt-1 font-medium">{qr.start_time.slice(0, 5)}-{qr.end_time.slice(0, 5)}</dd></div><div><dt className="text-xs uppercase tracking-wider text-slate-500">Room</dt><dd className="mt-1 font-medium">{qr.room}</dd></div><div><dt className="text-xs uppercase tracking-wider text-slate-500">Check-in window</dt><dd className="mt-1 font-medium">{qr.self_checkin_window_minutes} minutes</dd></div></dl>{qr.geofence_radius_meters != null ? <div className="mt-6 rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-4"><p className="font-semibold text-emerald-300">Campus location check active</p><p className="mt-1 text-sm text-slate-400">Teacher location was captured with +/-{Math.round(qr.teacher_location_accuracy_meters ?? 0)}m accuracy.</p></div> : <p className="mt-6 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-amber-200">Historical session: location attempts require teacher verification.</p>}</div>
    </section>}
    <section aria-label="Attendance counts" className="mb-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        { label: "Total students", value: counts.total, detail: "In this session roster", tone: "border-blue-500/30 bg-blue-500/10" },
        { label: "Present", value: counts.present, detail: "Present or late", tone: "border-emerald-500/35 bg-emerald-500/10" },
        { label: "Absent", value: counts.absent, detail: counts.pending ? `${counts.pending} needs review` : "No review needed", tone: "border-red-500/35 bg-red-500/10" },
        { label: "Attendance rate", value: `${attendanceRate}%`, detail: counts.remaining ? `${counts.remaining} awaiting check-in` : "Live check-in rate", tone: "border-violet-500/35 bg-violet-500/10" },
      ].map((item) => <div key={item.label} className={`rounded-xl border p-4 shadow-sm ${item.tone}`}><p className="text-sm font-medium text-slate-300">{item.label}</p><p className="mt-1 text-3xl font-semibold text-slate-50">{item.value}</p><p className="mt-1 text-xs text-slate-400">{item.detail}</p></div>)}
    </section>
    <section className="mb-8"><h2 className="mb-1 text-xl font-semibold">Location verification attempts</h2><p className="mb-3 text-sm text-slate-400">A student outside your selected boundary is held for review, not marked absent. Confirm only when you can verify the student is in class.</p><div className="table-wrap"><table><thead><tr><th>Student</th><th>Section</th><th>Reason</th><th>Distance from your location / boundary</th><th>Accuracy</th><th>Time</th><th>Actions</th></tr></thead><tbody>{exceptions.map((item) => <tr key={item.id}><td>{item.student_name}<br /><span className="text-slate-400">{item.roll_number}</span></td><td>{item.section_name}</td><td><StatusBadge status={item.reason} /></td><td>{meters(item.distance_meters)} / {meters(item.allowed_radius_meters)}</td><td>{meters(item.accuracy_meters)}</td><td>{new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td><td>{item.status === "pending" ? <div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => setDialog({ kind: "exception", item, decision: "confirm" })}>Confirm present</Button><Button size="sm" variant="danger" onClick={() => setDialog({ kind: "exception", item, decision: "reject" })}>Reject</Button></div> : <StatusBadge status={item.status} />}</td></tr>)}{!exceptions.length && <tr><td colSpan={7} className="p-0"><EmptyState title="No location exceptions" description="Check-in issues will appear here for review." /></td></tr>}</tbody></table></div></section>
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Live roster</h2>
          <p className="mt-1 text-sm text-slate-400">Status and distance update automatically from each student&apos;s latest location check-in.</p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-700 bg-slate-900/70 p-1" role="group" aria-label="Roster display">
          <Button type="button" size="sm" variant={rosterView === "grid" ? "primary" : "ghost"} aria-pressed={rosterView === "grid"} onClick={() => setRosterView("grid")}><GridIcon /> Cards</Button>
          <Button type="button" size="sm" variant={rosterView === "list" ? "primary" : "ghost"} aria-pressed={rosterView === "list"} onClick={() => setRosterView("list")}><ListIcon /> List</Button>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Roster status filter">
          {(["all", "present", "absent"] as const).map((filter) => {
            const count = filter === "all" ? counts.total : filter === "present" ? counts.present : counts.absent;
            const label = filter === "all" ? "All" : filter === "present" ? "Present" : "Absent";
            const active = rosterFilter === filter;
            return <button key={filter} type="button" aria-pressed={active} onClick={() => setRosterFilter(filter)} className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold transition ${active ? "border-emerald-400 bg-emerald-400 text-slate-950" : "border-slate-700 bg-slate-900/60 text-slate-200 hover:border-slate-500 hover:bg-slate-800"}`}><span>{label}</span><span className={`rounded-full px-1.5 py-0.5 text-xs ${active ? "bg-slate-950/15" : "bg-slate-800 text-slate-400"}`}>{count}</span></button>;
          })}
        </div>
        <label className="relative block min-w-[min(100%,18rem)] flex-1 sm:max-w-sm">
          <span className="sr-only">Search students</span>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 fill-none stroke-slate-400 stroke-2"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" strokeLinecap="round" /></svg>
          <input value={search} onChange={(event) => setSearch(event.target.value)} type="search" placeholder="Search by name or student number" className="min-h-10 w-full rounded-lg border border-slate-700 bg-slate-900/70 py-2 pl-10 pr-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/20" />
        </label>
      </div>
      {!rows.length ? <div className="panel"><EmptyState title="No students in this roster" description="Students enrolled in this session will appear here." /></div> : !visibleRows.length ? <div className="panel"><EmptyState title="No matching students" description="Try another status filter or search by name or student number." /></div> : rosterView === "grid" ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{visibleRows.map((row) => <article key={row.student_id} className={`rounded-2xl border-2 p-4 shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 ${rosterToneFor(row.status)}`}><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><ProfileAvatar name={row.student_name} className="h-12 w-12 text-base" /><div className="min-w-0"><h3 className="truncate font-semibold text-slate-50">{row.student_name}</h3><p className="mt-0.5 text-sm text-slate-300">Student no. {row.roll_number}</p></div></div><StatusBadge status={row.status} /></div><dl className="mt-4 grid grid-cols-2 gap-3 border-y border-current/20 py-3 text-sm"><div><dt className="text-slate-400">Check-in</dt><dd className="mt-1 font-medium text-slate-100">{timeLabel(row.check_in_time)}</dd></div><div><dt className="text-slate-400">Distance</dt><dd className="mt-1 font-medium text-slate-100">{row.distance_meters == null ? "Not recorded" : meters(row.distance_meters)}</dd></div></dl><div className="mt-3 rounded-lg border border-current/20 bg-slate-950/20 px-3 py-2 text-xs text-slate-300"><p className="font-medium text-slate-100">{distanceLabel(row)}</p>{row.location_accuracy_meters != null && <p className="mt-1 text-slate-400">Location accuracy: +/-{meters(row.location_accuracy_meters)}</p>}</div><label className="mt-4 block"><span className="sr-only">Correct attendance for {row.student_name}</span>{correctionSelect(row)}</label></article>)}</div> : <div className="space-y-3">{visibleRows.map((row) => <article key={row.student_id} className={`grid gap-4 rounded-xl border-2 p-4 shadow-sm md:grid-cols-[minmax(15rem,1.3fr)_auto_minmax(10rem,1fr)_minmax(9rem,.8fr)_minmax(10rem,.8fr)] md:items-center ${rosterToneFor(row.status)}`}><div className="flex min-w-0 items-center gap-3"><ProfileAvatar name={row.student_name} className="h-11 w-11 text-base" /><div className="min-w-0"><h3 className="truncate font-semibold text-slate-50">{row.student_name}</h3><p className="mt-0.5 text-sm text-slate-300">Student no. {row.roll_number}</p></div></div><StatusBadge status={row.status} /><div><p className="text-xs uppercase tracking-wide text-slate-500">Check-in</p><p className="mt-1 text-sm font-medium text-slate-100">{timeLabel(row.check_in_time)}</p></div><div><p className="text-xs uppercase tracking-wide text-slate-500">Distance from teacher</p><p className="mt-1 text-sm font-medium text-slate-100">{row.distance_meters == null ? "Not recorded" : meters(row.distance_meters)}</p><p className="mt-1 text-xs text-slate-400">{row.allowed_radius_meters == null ? "No boundary recorded" : `${meters(row.allowed_radius_meters)} allowed radius`}</p></div><label className="block"><span className="sr-only">Correct attendance for {row.student_name}</span>{correctionSelect(row)}</label></article>)}</div>}
      <p className="mt-4 text-sm text-slate-400">Showing {visibleRows.length} of {counts.total} students. Distance is calculated from the teacher location captured at session start to the student&apos;s approved check-in location.</p>
    </section>
    {dialogInfo && <ConfirmDialog open title={dialogInfo.title} description={dialogInfo.description} confirmLabel={dialogInfo.label} tone={dialogInfo.tone} requireReason={dialogInfo.reason} onClose={() => setDialog(null)} onConfirm={confirmAction} />}
  </div>;
}
