"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

const localDate = (value = new Date()) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

export default function Page() {
  const [rows, setRows] = useState<any[]>([]);
  const [data, setData] = useState<Record<string, any[]>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [scheduleDate, setScheduleDate] = useState(localDate());
  const [rangeDays, setRangeDays] = useState("8");
  const [filters, setFilters] = useState({ query: "", module: "", teacher: "", classType: "", section: "", occupancy: "" });

  const load = useCallback(async (fromDate = scheduleDate) => {
    setLoading(true);
    setError("");
    try {
      const names = ["modules", "teachers", "class-types"];
      const responses = await Promise.all([
        ...names.map((name) => api.get(`/api/v1/academic/${name}`)),
        api.get(`/api/v1/academic/routine-occurrences?date_from=${fromDate}&days=31`),
      ]);
      setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data])));
      setRows(responses.at(-1)?.data || []);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load canonical timetable");
    } finally {
      setLoading(false);
    }
  }, [scheduleDate]);

  useEffect(() => { void load(); }, [load]);

  const name = useCallback((key: string, id: number) => {
    const item = data[key]?.find((entry) => entry.id === id);
    return item ? (key === "modules" ? item.title : item.name) : "—";
  }, [data]);
  const occupancyStatus = (occurrence: any) =>
    occurrence.occupancy_status ?? (occurrence.cancelled || !occurrence.section_names?.length ? "empty" : "occupied");
  const visibleRows = useMemo(() => {
    const end = new Date(`${scheduleDate}T12:00:00`);
    end.setDate(end.getDate() + Number(rangeDays) - 1);
    const endDate = localDate(end);
    return rows.filter((occurrence) => {
      if (occurrence.date < scheduleDate || occurrence.date > endDate) return false;
      if (filters.module && String(occurrence.module_id) !== filters.module) return false;
      if (filters.teacher && String(occurrence.teacher_id) !== filters.teacher) return false;
      if (filters.classType && String(occurrence.class_type_id) !== filters.classType) return false;
      if (filters.section && !occurrence.section_names.some((section: string) => section.toLowerCase().includes(filters.section.toLowerCase()))) return false;
      if (filters.occupancy === "cancelled" && !occurrence.cancelled) return false;
      if (filters.occupancy === "occupied" && (occurrence.cancelled || occupancyStatus(occurrence) !== "occupied")) return false;
      if (filters.occupancy === "empty" && (occurrence.cancelled || occupancyStatus(occurrence) !== "empty")) return false;
      if (filters.query) {
        const haystack = [name("modules", occurrence.module_id), name("teachers", occurrence.teacher_id), occurrence.section_names.join(" "), occurrence.room].join(" ").toLowerCase();
        if (!haystack.includes(filters.query.toLowerCase())) return false;
      }
      return true;
    });
  }, [filters, name, rangeDays, rows, scheduleDate]);
  const selectedDateRows = visibleRows.filter((item) => item.date === scheduleDate);
  const upcoming = visibleRows.filter((item) => item.date !== scheduleDate && (filters.occupancy === "cancelled" || !item.cancelled)).slice(0, 5);
  const selectedDateOccupied = selectedDateRows.filter((item) => occupancyStatus(item) === "occupied").length;

  const item = (occurrence: any) => {
    const status = occupancyStatus(occurrence);
    return <article key={`${occurrence.routine_id}-${occurrence.date}`} className="border-t border-slate-800 px-5 py-4 first:border-t-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-slate-200">{occurrence.date} · {occurrence.start_time.slice(0, 5)}–{occurrence.end_time.slice(0, 5)}</p>
        <div className="flex flex-wrap gap-2">
          <Badge tone={status === "occupied" ? "success" : "neutral"}>{status === "occupied" ? "Occupied" : "Empty"}</Badge>
          {occurrence.override_id && <Badge tone="warning">Overridden</Badge>}
          {occurrence.cancelled && <Badge tone="danger">Cancelled</Badge>}
        </div>
      </div>
      <h3 className="mt-2 font-semibold">{name("modules", occurrence.module_id)}</h3>
      <p className="mt-1 text-sm text-slate-400">{occurrence.section_names.join(" + ")} · {name("teachers", occurrence.teacher_id)} · {occurrence.room}</p>
    </article>;
  };

  return <div>
    <PageHeader title="Administration dashboard" description="Filter the academic schedule by date, course, teacher, section, and occupancy before reviewing activity across the college." action={<Link href="/admin/routine" className="inline-flex min-h-10 items-center rounded-lg bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-300">Manage routine</Link>} />
    {error && <ErrorState title="Unable to load timetable" description={error} onRetry={() => void load()} />}
    {loading ? <div className="grid gap-5 lg:grid-cols-2"><LoadingState /><LoadingState /></div> : <>
      <section aria-label="Schedule metrics" className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="panel p-5"><p className="text-sm text-slate-400">Classes on selected date</p><p className="mt-2 text-3xl font-semibold">{selectedDateRows.length}</p></div>
        <div className="panel p-5"><p className="text-sm text-slate-400">Occupied on selected date</p><p className="mt-2 text-3xl font-semibold text-emerald-400">{selectedDateOccupied}</p></div>
        <div className="panel p-5"><p className="text-sm text-slate-400">Upcoming classes shown</p><p className="mt-2 text-3xl font-semibold">{upcoming.length}</p></div>
      </section>
      <section className="panel mb-6 p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Schedule filters</h2><p className="mt-1 text-sm text-slate-400">Filters apply to the selected date range and both schedule lists.</p></div><Button type="button" variant="ghost" onClick={() => setFilters({ query: "", module: "", teacher: "", classType: "", section: "", occupancy: "" })}>Clear filters</Button></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label><span className="field-label">Start date</span><input type="date" required value={scheduleDate} onChange={(event) => setScheduleDate(event.target.value || localDate())} /></label>
          <label><span className="field-label">Date range</span><select value={rangeDays} onChange={(event) => setRangeDays(event.target.value)}><option value="1">Selected date only</option><option value="7">Next 7 days</option><option value="31">Next 31 days</option></select></label>
          <label><span className="field-label">Search</span><input placeholder="Course, teacher, section, room" value={filters.query} onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))} /></label>
          <label><span className="field-label">Section</span><input placeholder="Any section" value={filters.section} onChange={(event) => setFilters((current) => ({ ...current, section: event.target.value }))} /></label>
          <label><span className="field-label">Module</span><select value={filters.module} onChange={(event) => setFilters((current) => ({ ...current, module: event.target.value }))}><option value="">All modules</option>{(data.modules || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.code} — {entry.title}</option>)}</select></label>
          <label><span className="field-label">Teacher</span><select value={filters.teacher} onChange={(event) => setFilters((current) => ({ ...current, teacher: event.target.value }))}><option value="">All teachers</option>{(data.teachers || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
          <label><span className="field-label">Class type</span><select value={filters.classType} onChange={(event) => setFilters((current) => ({ ...current, classType: event.target.value }))}><option value="">All class types</option>{(data["class-types"] || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
          <label><span className="field-label">Occupancy</span><select value={filters.occupancy} onChange={(event) => setFilters((current) => ({ ...current, occupancy: event.target.value }))}><option value="">All classes</option><option value="occupied">Occupied</option><option value="empty">Empty</option><option value="cancelled">Cancelled</option></select></label>
        </div>
        <div className="mt-4 flex justify-end"><Button type="button" size="sm" onClick={() => void load(scheduleDate)}>Reload schedule</Button></div>
      </section>
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel overflow-hidden"><h2 className="px-5 py-4 text-lg font-semibold">Classes on {scheduleDate}</h2>{selectedDateRows.map(item)}{!selectedDateRows.length && <EmptyState title="No classes match these filters" description="Try another date or clear one of the schedule filters." />}</section>
        <section className="panel overflow-hidden"><h2 className="px-5 py-4 text-lg font-semibold">Upcoming classes</h2>{upcoming.map(item)}{!upcoming.length && <EmptyState title="No upcoming classes" description="The next scheduled occurrences will appear here." />}</section>
      </div>
    </>}
  </div>;
}
