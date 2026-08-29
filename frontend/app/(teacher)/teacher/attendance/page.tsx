"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { PageHeader } from "@/components/ui/PageHeader";

type StudentRow = {
  attendance_id: number | null;
  student_id: number;
  student_name: string;
  roll_number: string;
  status: string;
};

type AttendanceClass = {
  routine_id: number;
  session_id: number | null;
  date: string;
  module_code: string;
  module_title: string;
  section_names: string[];
  start_time: string;
  end_time: string;
  room: string;
  cancelled: boolean;
  session_status: string | null;
  students: StudentRow[];
};

type PendingChange = { classItem: AttendanceClass; row: StudentRow; status: string };

const localDate = (value = new Date()) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const editableStatuses = ["present", "late", "absent", "leave", "bunk"];

export default function Page() {
  const today = localDate();
  const [selectedDate, setSelectedDate] = useState(today);
  const [classes, setClasses] = useState<AttendanceClass[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dialog, setDialog] = useState<PendingChange | null>(null);
  const [filters, setFilters] = useState({ query: "", section: "", student: "", status: "" });

  const load = useCallback(async (date = selectedDate) => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get<AttendanceClass[]>(`/api/v1/teacher/attendance?date=${encodeURIComponent(date)}`);
      setClasses(response.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load attendance for this date.");
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => { void load(); }, [load]);

  async function saveChange(reason: string) {
    if (!dialog) return;
    try {
      await api.put(`/api/v1/teacher/attendance/${dialog.classItem.routine_id}/${dialog.row.student_id}?date=${encodeURIComponent(selectedDate)}`, {
        status: dialog.status,
        reason,
      });
      setMessage(`${dialog.row.student_name}'s attendance was changed to ${dialog.status.replaceAll("_", " ")}.`);
      await load(selectedDate);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to save this attendance correction.");
      throw requestError;
    }
  }

  function classStatus(item: AttendanceClass) {
    if (item.cancelled) return <Badge tone="danger">Cancelled</Badge>;
    if (item.session_status === "completed") return <Badge tone="success">Saved</Badge>;
    if (item.session_status === "active") return <Badge tone="info">In progress</Badge>;
    return <Badge tone="neutral">Not recorded</Badge>;
  }

  const visibleClasses = useMemo(() => classes.map((item) => {
    const classText = [item.module_code, item.module_title, item.section_names.join(" "), item.room].join(" ").toLowerCase();
    const students = item.students.filter((row) => {
      if (filters.status && row.status !== filters.status) return false;
      if (filters.student && ![row.student_name, row.roll_number].join(" ").toLowerCase().includes(filters.student.toLowerCase())) return false;
      return true;
    });
    return { ...item, students, classText };
  }).filter((item) => {
    if (filters.query && !item.classText.includes(filters.query.toLowerCase())) return false;
    if (filters.section && !item.section_names.some((section) => section.toLowerCase().includes(filters.section.toLowerCase()))) return false;
    if ((filters.student || filters.status) && !item.students.length) return false;
    return true;
  }), [classes, filters]);

  return <div>
    <PageHeader title="Manual attendance" description="Choose today or an earlier date to review every class you teach and correct any student’s attendance. Each change is saved in the audit trail." action={<Button variant="outline" onClick={() => void load()}>Refresh</Button>} />
    <section className="panel mb-6 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><label className="block w-full max-w-xs"><span className="field-label">Attendance date</span><input type="date" max={today} value={selectedDate} onChange={event => setSelectedDate(event.target.value)} /><span className="helper-text">Future dates are not available for manual editing.</span></label><div className="flex flex-wrap gap-2"><Button variant={selectedDate === today ? "primary" : "outline"} onClick={() => setSelectedDate(today)}>Today</Button><Button variant="ghost" onClick={() => setSelectedDate(localDate(new Date(Date.now() - 86400000)))}>Yesterday</Button></div></div>
      <div className="mt-5 border-t border-slate-800 pt-5"><div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Attendance filters</h2><p className="mt-1 text-sm text-slate-400">Narrow the classes or students shown for the selected date.</p></div><Button type="button" variant="ghost" onClick={() => setFilters({ query: "", section: "", student: "", status: "" })}>Clear filters</Button></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label><span className="field-label">Class search</span><input placeholder="Module or room" value={filters.query} onChange={event => setFilters(current => ({ ...current, query: event.target.value }))} /></label><label><span className="field-label">Section</span><input placeholder="Any section" value={filters.section} onChange={event => setFilters(current => ({ ...current, section: event.target.value }))} /></label><label><span className="field-label">Student search</span><input placeholder="Name or roll number" value={filters.student} onChange={event => setFilters(current => ({ ...current, student: event.target.value }))} /></label><label><span className="field-label">Attendance status</span><select value={filters.status} onChange={event => setFilters(current => ({ ...current, status: event.target.value }))}><option value="">All statuses</option>{editableStatuses.map(status => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}<option value="not_checked_in">Not checked in</option><option value="pending_verification">Pending verification</option><option value="rejected">Rejected</option></select></label></div></div>
    </section>
    {message && <p role="status" className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</p>}
    {error && <div className="mb-4"><ErrorState title="Unable to load attendance" description={error} onRetry={() => void load()} /></div>}
    {loading ? <LoadingState label="Loading attendance classes" /> : !visibleClasses.length ? <div className="panel"><EmptyState title={classes.length ? "No classes match these filters" : "No classes on this date"} description={classes.length ? "Try clearing a class, student, or status filter." : "Only sections and classes assigned to you appear here."} /></div> : <div className="space-y-6">
      {visibleClasses.map(item => <section key={item.routine_id} className={`panel overflow-hidden ${item.cancelled ? "opacity-75" : ""}`}>
        <div className="flex flex-col gap-4 border-b border-slate-800 p-5 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold uppercase tracking-wider text-emerald-400">{item.module_code}</span>{classStatus(item)}</div><h2 className="mt-2 text-xl font-semibold">{item.module_title}</h2><p className="mt-1 text-sm text-slate-400">{item.section_names.join(" + ")} · {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)} · {item.room}</p></div>
          <p className="max-w-sm text-sm leading-6 text-slate-400">{item.session_id ? "Attendance session available for editing." : "No session exists yet. Your first manual change will create this date’s attendance session."}</p>
        </div>
        <div className="table-wrap rounded-none border-0"><table><thead><tr><th>Student</th><th>Roll</th><th>Current status</th><th>Change attendance</th></tr></thead><tbody>{item.students.map(row => <tr key={row.student_id}><td className="font-medium text-slate-200">{row.student_name}</td><td>{row.roll_number}</td><td><StatusBadge status={row.status} /></td><td><select aria-label={`Change attendance for ${row.student_name}`} disabled={item.cancelled} value={row.status} onChange={event => { if (editableStatuses.includes(event.target.value) && event.target.value !== row.status) setDialog({ classItem: item, row, status: event.target.value }); }}><option value={row.status}>{row.status.replaceAll("_", " ")}</option>{editableStatuses.filter(status => status !== row.status).map(status => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></td></tr>)}</tbody></table></div>
      </section>)}
    </div>}
    {dialog && <ConfirmDialog open title={`Change ${dialog.row.student_name} to ${dialog.status.replaceAll("_", " ")}?`} description="This correction applies to the selected class date and is recorded in the attendance audit trail." confirmLabel="Save correction" requireReason onClose={() => setDialog(null)} onConfirm={saveChange} />}
  </div>;
}
