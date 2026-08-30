"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { downloadFile } from "@/lib/download";

type RoutineOccurrence = {
  routine_id: number;
  date: string;
  start_time: string;
  end_time: string;
  module_id: number;
  teacher_id: number;
  class_type_id: number;
  room: string;
  original_room: string;
  section_names?: string[];
  cancelled: boolean;
};

type AttendanceRecord = {
  session_id: number;
  date: string;
  weekday: string;
  subject_id: number;
  subject_name: string;
  subject_code: string | null;
  class_type_id: number | null;
  class_type_name: string | null;
  status: string;
  check_in_time: string | null;
};

type AttendanceSubject = {
  subject_id: number;
  subject_name: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
};

type AttendanceDay = {
  date: string;
  weekday: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
  records: AttendanceRecord[];
};

type AttendanceClassType = {
  key: string;
  name: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
};

type AttendanceReport = {
  student_id: number;
  date_from: string | null;
  date_to: string | null;
  present: number;
  absent: number;
  total: number;
  overall_percentage: number;
  subjects: AttendanceSubject[];
  days: AttendanceDay[];
  attendance_threshold_percent: number;
  minimum_observations: number;
};

const localDate = (value = new Date()) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function shiftDate(days: number) {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return localDate(value);
}

const initialDateTo = localDate();
const initialDateFrom = shiftDate(-29);
const scheduleDateMax = localDate(new Date(Date.now() + 7 * 86400000));

type AnalysisMode = "day" | "subject";
type Period = "last-30" | "this-month" | "all-time" | "custom";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function percentage(value: number) {
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function attended(status: string) {
  return status === "present" || status === "late";
}

function currentMonthStart() {
  const value = new Date();
  return localDate(new Date(value.getFullYear(), value.getMonth(), 1));
}

function rangeLabel(dateFrom: string | null, dateTo: string | null) {
  if (!dateFrom && !dateTo) return "all completed classes";
  if (dateFrom && dateTo) return `${formatDate(dateFrom)} – ${formatDate(dateTo)}`;
  return dateFrom ? `from ${formatDate(dateFrom)}` : `through ${formatDate(dateTo!)}`;
}

function csvCell(value: string | number | null | undefined) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export default function Page() {
  const [occurrences, setOccurrences] = useState<RoutineOccurrence[]>([]);
  const [catalog, setCatalog] = useState<Record<string, any[]>>({});
  const [scheduleError, setScheduleError] = useState("");
  const [attendanceError, setAttendanceError] = useState("");
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [attendanceLoading, setAttendanceLoading] = useState(true);
  const [attendance, setAttendance] = useState<AttendanceReport | null>(null);
  const [scheduleFilters, setScheduleFilters] = useState({ date: "", module: "", teacher: "", classType: "", query: "" });
  const [dateFrom, setDateFrom] = useState(initialDateFrom);
  const [dateTo, setDateTo] = useState(initialDateTo);
  const [subjectFilter, setSubjectFilter] = useState("");
  const [classTypeFilter, setClassTypeFilter] = useState("");
  const [dayFilter, setDayFilter] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("day");
  const [period, setPeriod] = useState<Period>("last-30");
  const [exportError, setExportError] = useState("");

  const loadSchedule = useCallback(async () => {
    setScheduleLoading(true);
    setScheduleError("");
    try {
      const today = localDate();
      const [catalogResponse, occurrenceResponse] = await Promise.all([
        api.get("/api/v1/academic/catalog"),
        api.get(`/api/v1/academic/routines/me/occurrences?date_from=${today}&days=8`),
      ]);
      setCatalog(catalogResponse.data);
      setOccurrences(occurrenceResponse.data || []);
    } catch (requestError: any) {
      setScheduleError(requestError.response?.data?.detail ?? "Unable to load your routine");
    } finally {
      setScheduleLoading(false);
    }
  }, []);

  const loadAttendance = useCallback(async (from?: string, to?: string) => {
    setAttendanceLoading(true);
    setAttendanceError("");
    try {
      const params = new URLSearchParams();
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
      const query = params.toString();
      const response = await api.get<AttendanceReport>(`/api/v1/analytics/my-attendance${query ? `?${query}` : ""}`);
      setAttendance(response.data);
    } catch (requestError: any) {
      setAttendanceError(requestError.response?.data?.detail ?? "Unable to load your attendance");
    } finally {
      setAttendanceLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSchedule();
    void loadAttendance(initialDateFrom, initialDateTo);
  }, [loadAttendance, loadSchedule]);

  const name = useCallback((key: string, id: number) => {
    const item = catalog[key]?.find((entry) => entry.id === id);
    return item ? (key === "modules" ? item.title : item.name) : "—";
  }, [catalog]);

  const filteredSchedule = useMemo(() => occurrences.filter((item) => {
    if (scheduleFilters.date && item.date !== scheduleFilters.date) return false;
    if (scheduleFilters.module && String(item.module_id) !== scheduleFilters.module) return false;
    if (scheduleFilters.teacher && String(item.teacher_id) !== scheduleFilters.teacher) return false;
    if (scheduleFilters.classType && String(item.class_type_id) !== scheduleFilters.classType) return false;
    if (scheduleFilters.query) {
      const haystack = [name("modules", item.module_id), name("teachers", item.teacher_id), item.room].join(" ").toLowerCase();
      if (!haystack.includes(scheduleFilters.query.toLowerCase())) return false;
    }
    return true;
  }), [name, occurrences, scheduleFilters]);
  const scheduleStart = scheduleFilters.date || localDate();
  const today = filteredSchedule.filter((item) => item.date === scheduleStart);
  const next = filteredSchedule.find((item) => item.date >= scheduleStart && !item.cancelled);
  const card = (item: RoutineOccurrence) => (
    <article key={`${item.routine_id}-${item.date}`} className={`panel p-5 ${item.cancelled ? "border-red-500/30 bg-red-500/5" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-lg font-semibold">{item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</p>
        <Badge tone={item.cancelled ? "danger" : "info"}>{item.cancelled ? "Cancelled" : name("class-types", item.class_type_id)}</Badge>
      </div>
      <h3 className="mt-3 text-lg font-semibold">{name("modules", item.module_id)}</h3>
      <p className="mt-2 text-sm text-slate-400">{name("teachers", item.teacher_id)} · {item.room}</p>
      {item.room !== item.original_room && !item.cancelled && <p className="mt-2 text-sm text-amber-300">Room changed from {item.original_room}</p>}
    </article>
  );

  const view = useMemo(() => {
    if (!attendance) return { records: [], days: [], subjects: [], classTypes: [] as AttendanceClassType[], present: 0, absent: 0, total: 0, overall: 0 };
    const includesRecord = (record: AttendanceRecord) =>
      (!subjectFilter || String(record.subject_id) === subjectFilter) && (!classTypeFilter || String(record.class_type_id ?? "legacy") === classTypeFilter) && (!dayFilter || record.date === dayFilter);
    const records = attendance.days.flatMap((day) => day.records).filter(includesRecord);
    const subjects = new Map<number, AttendanceSubject>();
    const classTypes = new Map<string, AttendanceClassType>();
    const days = attendance.days
      .map((day) => {
        const dayRecords = day.records.filter(includesRecord);
        const present = dayRecords.filter((record) => attended(record.status)).length;
        return { ...day, records: dayRecords, present, absent: dayRecords.length - present, total: dayRecords.length, percentage: dayRecords.length ? (100 * present) / dayRecords.length : 0 };
      })
      .filter((day) => day.records.length);
    records.forEach((record) => {
      const item = subjects.get(record.subject_id) ?? { subject_id: record.subject_id, subject_name: record.subject_name, present: 0, absent: 0, total: 0, percentage: 0 };
      item.total += 1;
      if (attended(record.status)) item.present += 1;
      else item.absent += 1;
      item.percentage = (100 * item.present) / item.total;
      subjects.set(record.subject_id, item);
      const typeKey = String(record.class_type_id ?? "legacy");
      const classType = classTypes.get(typeKey) ?? { key: typeKey, name: record.class_type_name ?? "Other class type", present: 0, absent: 0, total: 0, percentage: 0 };
      classType.total += 1;
      if (attended(record.status)) classType.present += 1;
      else classType.absent += 1;
      classType.percentage = (100 * classType.present) / classType.total;
      classTypes.set(typeKey, classType);
    });
    const present = records.filter((record) => attended(record.status)).length;
    return { records, days, subjects: [...subjects.values()].sort((left, right) => left.subject_name.localeCompare(right.subject_name)), classTypes: [...classTypes.values()].sort((left, right) => left.name.localeCompare(right.name)), present, absent: records.length - present, total: records.length, overall: records.length ? (100 * present) / records.length : 0 };
  }, [attendance, classTypeFilter, dayFilter, subjectFilter]);

  function applyDateFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((dateFrom && !dateTo) || (!dateFrom && dateTo) || (dateFrom && dateTo && dateFrom > dateTo)) {
      setAttendanceError("Choose a valid date range. The start date must be on or before the end date.");
      return;
    }
    setPeriod(dateFrom || dateTo ? "custom" : "all-time");
    setDayFilter("");
    void loadAttendance(dateFrom || undefined, dateTo || undefined);
  }

  function setQuickPeriod(nextPeriod: Exclude<Period, "custom">) {
    setPeriod(nextPeriod);
    setDayFilter("");
    if (nextPeriod === "all-time") {
      setDateFrom("");
      setDateTo("");
      void loadAttendance();
      return;
    }
    const from = nextPeriod === "this-month" ? currentMonthStart() : initialDateFrom;
    setDateFrom(from);
    setDateTo(initialDateTo);
    void loadAttendance(from, initialDateTo);
  }

  function exportFilteredAttendance() {
    if (!attendance) return;
    setExportError("");
    const selectedSubject = attendance.subjects.find((subject) => String(subject.subject_id) === subjectFilter)?.subject_name ?? "All subjects";
    const selectedClassType = attendance.days.flatMap((day) => day.records).find((record) => String(record.class_type_id ?? "legacy") === classTypeFilter)?.class_type_name ?? "All class types";
    const rows: (string | number | null | undefined)[][] = [
      ["Attendance analysis"],
      ["Period", rangeLabel(attendance.date_from, attendance.date_to)],
      ["Day filter", dayFilter ? formatDate(dayFilter) : "All days"],
      ["Subject filter", selectedSubject],
      ["Class type filter", selectedClassType],
      [],
      ["Attendance rate", percentage(view.overall)],
      ["Present / late", view.present],
      ["Absent / other", view.absent],
      ["Completed classes", view.total],
      [],
      ["Subject", "Present", "Absent", "Total", "Attendance percentage"],
      ...view.subjects.map((subject) => [subject.subject_name, subject.present, subject.absent, subject.total, percentage(subject.percentage)]),
      [],
      ["Date", "Weekday", "Subject", "Subject code", "Status", "Check-in time"],
      ...view.records.map((record) => [record.date, record.weekday, record.subject_name, record.subject_code, record.status, record.check_in_time]),
    ];
    const file = new Blob([rows.map((row) => row.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = href;
    link.download = "my_filtered_attendance_analysis.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(href), 1_000);
  }

  async function exportAllTimeAnalysis() {
    setExportError("");
    try {
      await downloadFile("/api/v1/analytics/my-attendance-summary.csv", "my_all_time_attendance_analysis.csv");
    } catch (requestError: any) {
      setExportError(requestError.response?.data?.detail ?? "Unable to export the all-time attendance analysis.");
    }
  }

  useEffect(() => {
    if (subjectFilter && attendance && !attendance.subjects.some((subject) => String(subject.subject_id) === subjectFilter)) setSubjectFilter("");
  }, [attendance, subjectFilter]);

  useEffect(() => {
    // The timetable's module IDs are the same IDs used by routine-session
    // attendance records, so selecting a module also focuses the analytics.
    setSubjectFilter(scheduleFilters.module);
  }, [scheduleFilters.module]);

  useEffect(() => {
    if (classTypeFilter && attendance && !attendance.days.flatMap((day) => day.records).some((record) => String(record.class_type_id ?? "legacy") === classTypeFilter)) setClassTypeFilter("");
  }, [attendance, classTypeFilter]);

  useEffect(() => {
    if (dayFilter && attendance && !attendance.days.some((day) => day.date === dayFilter)) setDayFilter("");
  }, [attendance, dayFilter]);

  const overallTone = attendance && view.total >= attendance.minimum_observations && view.overall < attendance.attendance_threshold_percent ? "danger" : "success";
  const overallLabel = attendance && view.total < attendance.minimum_observations ? "Building baseline" : view.overall < (attendance?.attendance_threshold_percent ?? 0) ? "Needs attention" : "On track";
  const mostMissedClassType = view.classTypes.toSorted((left, right) => left.percentage - right.percentage)[0];
  const selectedSubject = attendance?.subjects.find((subject) => String(subject.subject_id) === subjectFilter) ?? null;

  return (
    <div>
      <PageHeader title="Student dashboard" description="Your classes, routine, and attendance at a glance." action={<Link href="/student/check-in" className="inline-flex min-h-10 items-center rounded-lg bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-300">Check in</Link>} />

      {scheduleError && <ErrorState title="Unable to load your schedule" description={scheduleError} onRetry={() => void loadSchedule()} />}
      {scheduleLoading ? <LoadingState label="Loading student dashboard" /> : <>
        <section className="panel mb-6 p-5">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Schedule filters</h2><p className="mt-1 text-sm text-slate-400">Filter the classes loaded for today and the next 7 days.</p></div><Button type="button" variant="ghost" onClick={() => setScheduleFilters({ date: "", module: "", teacher: "", classType: "", query: "" })}>Clear filters</Button></div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label><span className="field-label">Class date</span><input type="date" min={localDate()} max={scheduleDateMax} value={scheduleFilters.date} onChange={(event) => setScheduleFilters((current) => ({ ...current, date: event.target.value }))} /></label>
            <label><span className="field-label">Module</span><select value={scheduleFilters.module} onChange={(event) => setScheduleFilters((current) => ({ ...current, module: event.target.value }))}><option value="">All modules</option>{(catalog.modules || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.code} — {entry.title}</option>)}</select></label>
            <label><span className="field-label">Teacher</span><select value={scheduleFilters.teacher} onChange={(event) => setScheduleFilters((current) => ({ ...current, teacher: event.target.value }))}><option value="">All teachers</option>{(catalog.teachers || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
            <label><span className="field-label">Class type</span><select value={scheduleFilters.classType} onChange={(event) => setScheduleFilters((current) => ({ ...current, classType: event.target.value }))}><option value="">All class types</option>{(catalog["class-types"] || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
            <label><span className="field-label">Search</span><input placeholder="Course or room" value={scheduleFilters.query} onChange={(event) => setScheduleFilters((current) => ({ ...current, query: event.target.value }))} /></label>
          </div>
        </section>
        <section>
          <h2 className="mb-3 text-lg font-semibold">{scheduleFilters.date ? `Classes on ${scheduleFilters.date}` : "Today's classes"}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {today.map(card)}
            {!today.length && <div className="panel md:col-span-2"><EmptyState title="No classes scheduled today" description="Your next scheduled class will appear below." /></div>}
          </div>
        </section>
        <section className="mt-8">
          <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">Next class</h2><Link className="interactive-link text-sm" href="/student/routine">View full routine</Link></div>
          {next ? card(next) : <div className="panel"><EmptyState title="No upcoming class" description="Your assigned routine will appear here when available." /></div>}
        </section>
      </>}

      <section className="mt-10" aria-labelledby="attendance-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div><h2 id="attendance-heading" className="text-xl font-semibold">Attendance analytics</h2><p className="mt-1 text-sm text-slate-400">Review your attendance by date, day, and subject. Only completed classes are included.</p></div>
          <Link className="interactive-link text-sm" href="/student/reports">Open full report</Link>
        </div>

        <div className="panel p-4">
          <div role="tablist" aria-label="Attendance analysis view" className="flex flex-wrap gap-2 border-b border-slate-800 pb-4">
            <button type="button" role="tab" aria-selected={analysisMode === "day"} onClick={() => setAnalysisMode("day")} className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${analysisMode === "day" ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-800"}`}>Day-wise</button>
            <button type="button" role="tab" aria-selected={analysisMode === "subject"} onClick={() => setAnalysisMode("subject")} className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${analysisMode === "subject" ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-800"}`}>Subject-wise</button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm text-slate-400">Period</span>
            {(["last-30", "this-month", "all-time"] as const).map((item) => {
              const label = item === "last-30" ? "Last 30 days" : item === "this-month" ? "This month" : "All time";
              return <button key={item} type="button" onClick={() => setQuickPeriod(item)} className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${period === item ? "border-emerald-400 bg-emerald-400/15 text-emerald-200" : "border-slate-700 text-slate-300 hover:border-slate-500 hover:bg-slate-800/60"}`}>{label}</button>;
            })}
          </div>
          <form onSubmit={applyDateFilter} className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <label><span className="field-label">From date</span><input aria-label="Attendance start date" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="w-full" /></label>
            <label><span className="field-label">To date</span><input aria-label="Attendance end date" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="w-full" /></label>
            <Button type="submit" loading={attendanceLoading}>Apply custom dates</Button>
          </form>
        </div>

        {attendanceError && <div className="mt-4"><ErrorState title="Unable to load attendance analytics" description={attendanceError} onRetry={() => void loadAttendance(dateFrom || undefined, dateTo || undefined)} /></div>}
        {attendanceLoading ? <div className="mt-5"><LoadingState label="Loading attendance analytics" /></div> : attendance && <>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <div><p className="text-sm text-slate-400">Showing {rangeLabel(attendance.date_from, attendance.date_to)}</p><p className="mt-1 text-xs text-slate-500">Filters update the cards, analysis, and exported CSV.</p></div>
            <div className="flex flex-wrap gap-2"><Button type="button" size="sm" variant="outline" onClick={exportFilteredAttendance}>Export filtered CSV</Button><Button type="button" size="sm" variant="outline" onClick={() => void exportAllTimeAnalysis()}>All-time analysis CSV</Button></div>
          </div>
          {selectedSubject && <p className="mt-2 text-sm font-medium text-emerald-300">Showing attendance for: {selectedSubject.subject_name}</p>}
          {exportError && <p className="mt-3 text-sm text-red-300" role="alert">{exportError}</p>}
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <label><span className="field-label">Subject</span><select aria-label="Filter attendance by subject" value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)} className="w-full"><option value="">All subjects</option>{attendance.subjects.map((subject) => <option key={subject.subject_id} value={subject.subject_id}>{subject.subject_name}</option>)}</select></label>
            <label><span className="field-label">Class type</span><select aria-label="Filter attendance by class type" value={classTypeFilter} onChange={(event) => setClassTypeFilter(event.target.value)} className="w-full"><option value="">All class types</option>{[...new Map(attendance.days.flatMap((day) => day.records).map((record) => [String(record.class_type_id ?? "legacy"), record.class_type_name ?? "Other class type"]))].map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
            <label><span className="field-label">Specific day</span><input aria-label="Filter attendance by day" type="date" value={dayFilter} onChange={(event) => setDayFilter(event.target.value)} className="w-full" /></label>
          </div>
          {(subjectFilter || classTypeFilter || dayFilter) && <button type="button" onClick={() => { setSubjectFilter(""); setClassTypeFilter(""); setDayFilter(""); }} className="mt-3 text-sm font-semibold text-emerald-300 hover:text-emerald-200">Clear attendance filters</button>}

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <div className="panel p-4"><p className="text-sm text-slate-400">Attendance rate</p><p className={`mt-2 text-3xl font-semibold ${overallTone === "danger" ? "text-red-300" : "text-emerald-300"}`}>{percentage(view.overall)}</p><p className="mt-2 text-xs text-slate-400">Target: {percentage(attendance.attendance_threshold_percent)}</p></div>
            <div className="panel p-4"><p className="text-sm text-slate-400">Present / late</p><p className="mt-2 text-3xl font-semibold text-slate-50">{view.present}</p><p className="mt-2 text-xs text-slate-400">Classes attended</p></div>
            <div className="panel p-4"><p className="text-sm text-slate-400">Absent / other</p><p className="mt-2 text-3xl font-semibold text-slate-50">{view.absent}</p><p className="mt-2 text-xs text-slate-400">Absent, leave, or bunk</p></div>
            <div className="panel p-4"><p className="text-sm text-slate-400">Completed classes</p><p className="mt-2 text-3xl font-semibold text-slate-50">{view.total}</p><p className="mt-2 text-xs text-slate-400">Across {view.days.length} day{view.days.length === 1 ? "" : "s"}</p></div>
            <div className="panel p-4"><p className="text-sm text-slate-400">Most missed class type</p><p className="mt-2 truncate text-xl font-semibold text-slate-50">{mostMissedClassType?.name ?? "No data"}</p><p className="mt-2 text-xs text-slate-400">{mostMissedClassType ? `${percentage(mostMissedClassType.percentage)} attendance` : "Complete classes to see insight"}</p></div>
          </div>

          {!view.total ? <div className="panel mt-5"><EmptyState title="No completed classes in this range" description="Try widening the date range or choose another subject." /></div> : <>
            <div className="mt-5 grid gap-5">
              <section className={`panel p-5 ${analysisMode === "day" ? "" : "hidden"}`}><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">Day-wise attendance trend</h3><p className="mt-1 text-sm text-slate-400">Each bar represents your attendance for that day.</p></div><Badge tone={view.total < attendance.minimum_observations ? "neutral" : overallTone}>{overallLabel}</Badge></div><div className="mt-6 flex h-44 items-end gap-2 overflow-x-auto border-b border-slate-800 pb-0">{[...view.days].reverse().map((day) => <div key={day.date} className="flex min-w-10 flex-1 flex-col items-center justify-end gap-2"><span className="text-[10px] text-slate-400">{percentage(day.percentage)}</span><div title={`${formatDate(day.date)}: ${percentage(day.percentage)}`} className={`w-full min-w-5 rounded-t-md ${day.percentage < attendance.attendance_threshold_percent ? "bg-red-400/80" : "bg-emerald-400/80"}`} style={{ height: `${Math.max(day.percentage, 8)}%` }} /><span className="pb-2 text-[10px] text-slate-400">{day.date.slice(5)}</span></div>)}</div></section>
              <section className={`panel p-5 ${analysisMode === "subject" ? "" : "hidden"}`}><div><h3 className="font-semibold">Subject-wise attendance</h3><p className="mt-1 text-sm text-slate-400">Compare attendance across your subjects.</p></div><div className="mt-5 space-y-4">{view.subjects.map((subject) => { const belowThreshold = subject.total >= attendance.minimum_observations && subject.percentage < attendance.attendance_threshold_percent; return <div key={subject.subject_id}><div className="flex items-center justify-between gap-3 text-sm"><span className="truncate font-medium">{subject.subject_name}</span><span className="shrink-0 font-semibold">{percentage(subject.percentage)}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className={belowThreshold ? "h-full bg-red-400" : "h-full bg-emerald-400"} style={{ width: `${Math.min(subject.percentage, 100)}%` }} /></div><p className="mt-1 text-xs text-slate-400">{subject.present} attended · {subject.absent} missed · {subject.total} total{subject.total < attendance.minimum_observations ? " · building baseline" : ""}</p></div>; })}</div></section>
            </div>

            <section className={`mt-5 ${analysisMode === "day" ? "" : "hidden"}`}><div className="mb-3"><h3 className="text-xl font-semibold">Day-wise attendance</h3><p className="mt-1 text-sm text-slate-400">See exactly which subjects you attended on each day.</p></div><div className="grid gap-4 lg:grid-cols-2">{view.days.map((day) => <article key={day.date} className="panel p-5"><div className="flex items-start justify-between gap-3"><div><h4 className="font-semibold">{formatDate(day.date)}</h4><p className="mt-1 text-sm text-slate-400">{day.weekday} · {day.total} class{day.total === 1 ? "" : "es"}</p></div><Badge tone={day.percentage < attendance.attendance_threshold_percent ? "danger" : "success"}>{percentage(day.percentage)}</Badge></div><div className="mt-4 divide-y divide-slate-800">{day.records.map((record) => <div key={`${record.session_id}-${record.subject_id}`} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><p className="truncate text-sm font-medium">{record.subject_name}</p>{record.subject_code && <p className="mt-0.5 text-xs text-slate-400">{record.subject_code}</p>}</div><StatusBadge status={record.status} /></div>)}</div></article>)}</div></section>
          </>}
        </>}
      </section>
    </div>
  );
}
