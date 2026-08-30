"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { getBestFreshPosition, hasSecureDeviceContext, locationFailureReason } from "@/lib/geolocation";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { RoutineScheduleCards } from "@/components/RoutineScheduleCards";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const localDate = (value = new Date()) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
type PendingSessionStart = { routineId: number; latitude: number; longitude: number; accuracy: number };

export default function Page() {
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [occurrences, setOccurrences] = useState<any[]>([]);
  const [data, setData] = useState<Record<string, any[]>>({});
  const [error, setError] = useState("");
  const [startingId, setStartingId] = useState<number | null>(null);
  const [startStatus, setStartStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingStart, setPendingStart] = useState<PendingSessionStart | null>(null);
  const [locationRetryRoutineId, setLocationRetryRoutineId] = useState<number | null>(null);
  const [radiusInput, setRadiusInput] = useState("150");
  const [filters, setFilters] = useState({ query: "", module: "", section: "", classType: "", day: "" });

  async function load() {
    setError("");
    setLocationRetryRoutineId(null);
    try {
      const today = localDate();
      const [routineResponse, catalogResponse, occurrenceResponse] = await Promise.all([
        api.get("/api/v1/academic/teachers/me/routines"),
        api.get("/api/v1/academic/catalog"),
        api.get(`/api/v1/academic/teachers/me/occurrences?date_from=${today}&days=8`),
      ]);
      setRows(routineResponse.data);
      setData(catalogResponse.data);
      setOccurrences(occurrenceResponse.data || []);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load canonical routine");
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  const text = useCallback((key: string, id: number) => {
    const item = data[key]?.find((entry) => entry.id === id);
    if (!item) return String(id);
    if (key === "modules") return `${item.code} — ${item.title}`;
    if (key === "time-slots") return `${item.start_time?.slice(0, 5)}–${item.end_time?.slice(0, 5)}`;
    if (key === "rooms") return `${data.blocks?.find((entry) => entry.id === item.block_id)?.name ?? ""} / ${item.name}`;
    return item.name || item.code;
  }, [data]);

  async function start(routineId: number) {
    if (!hasSecureDeviceContext()) {
      setError("Starting a QR attendance session requires a secure HTTPS connection so the browser can share your classroom location.");
      return;
    }
    setStartingId(routineId);
    setError("");
    setLocationRetryRoutineId(null);
    setStartStatus("Getting your classroom location (this can take up to 30 seconds)…");
    try {
      const position = await getBestFreshPosition();
      setPendingStart({ routineId, latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy });
      setLocationRetryRoutineId(null);
      setStartStatus(`Location captured with +/-${Math.round(position.coords.accuracy)}m accuracy. Choose the attendance boundary, then start the QR session.`);
      setStartingId(null);
      return;
    } catch (requestError: any) {
      setLocationRetryRoutineId(routineId);
      const detail = requestError.response?.data?.detail;
      if (detail) setError(detail);
      else {
        const reason = locationFailureReason(requestError);
        setError(reason === "LOCATION_DENIED"
          ? "Location permission is required to create the classroom geofence. Allow location access and retry."
          : reason === "LOCATION_TIMEOUT"
            ? "A fresh classroom location could not be obtained within 30 seconds. Check that location services are on, allow location for this site, then retry."
            : "Classroom location is unavailable on this device. Check location services and the browser permission, then retry.");
      }
      setStartStatus("");
      setStartingId(null);
    }
  }

  async function startSession() {
    if (!pendingStart) return;
    const radius = Number(radiusInput);
    if (!Number.isFinite(radius) || radius <= 0) {
      setError("Enter a boundary greater than 0 meters.");
      return;
    }
    setStartingId(pendingStart.routineId);
    setError("");
    setLocationRetryRoutineId(null);
    setStartStatus("Creating the QR attendance session…");
    try {
      const response = await api.post(`/api/v1/routine-sessions/${pendingStart.routineId}/start`, {
        latitude: pendingStart.latitude,
        longitude: pendingStart.longitude,
        accuracy_meters: pendingStart.accuracy,
        geofence_radius_meters: radius,
      });
      router.push(`/teacher/sessions/${response.data.id}`);
    } catch (requestError: any) {
      const detail = requestError.response?.data?.detail ?? "Unable to start this attendance session.";
      setError(detail);
      setStartStatus("");
      setStartingId(null);
      if (String(detail).toLowerCase().includes("location accuracy")) {
        setPendingStart(null);
        setLocationRetryRoutineId(pendingStart.routineId);
      }
    }
  }

  const filteredRows = useMemo(() => rows.filter((row) => {
    if (filters.module && String(row.module_id) !== filters.module) return false;
    if (filters.classType && String(row.class_type_id) !== filters.classType) return false;
    if (filters.day && String(row.day_of_week) !== filters.day) return false;
    if (filters.section && !(row.section_names || []).some((section: string) => section.toLowerCase().includes(filters.section.toLowerCase()))) return false;
    if (filters.query) {
      const haystack = [text("modules", row.module_id), row.section_names?.join(" "), text("rooms", row.room_id)].join(" ").toLowerCase();
      if (!haystack.includes(filters.query.toLowerCase())) return false;
    }
    return true;
  }), [filters, rows, text]);
  const filteredOccurrences = useMemo(() => occurrences.filter((item) => {
    if (filters.module && String(item.module_id) !== filters.module) return false;
    if (filters.classType && String(item.class_type_id) !== filters.classType) return false;
    if (filters.day && String((new Date(`${item.date}T12:00:00`).getDay() + 6) % 7) !== filters.day) return false;
    if (filters.section && !item.section_names.some((section: string) => section.toLowerCase().includes(filters.section.toLowerCase()))) return false;
    if (filters.query) {
      const haystack = [text("modules", item.module_id), item.section_names.join(" "), item.room].join(" ").toLowerCase();
      if (!haystack.includes(filters.query.toLowerCase())) return false;
    }
    return true;
  }), [filters, occurrences, text]);
  const today = filteredOccurrences.filter((item) => item.date === localDate());
  const next = filteredOccurrences.find((item) => !item.cancelled);
  const occurrenceCard = (item: any) => <article key={`${item.routine_id}-${item.date}`} className={`panel p-5 ${item.cancelled ? "border-red-500/40 bg-red-500/5" : ""}`}>
    <div className="flex items-start justify-between gap-3"><p className="text-lg font-semibold text-slate-100">{item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</p><Badge tone={item.cancelled?"danger":"info"}>{item.cancelled?"Cancelled":text("class-types", item.class_type_id)}</Badge></div>
    <h3 className="mt-3 text-lg font-semibold">{text("modules", item.module_id)}</h3>
    <p className="mt-2 text-sm text-slate-300">{item.section_names.join(" + ")} · {item.room}</p>
    {item.room !== item.original_room && <p className="text-amber-300">Original room: {item.original_room} · Effective room: {item.room}</p>}
    {item.teacher_id !== item.original_teacher_id && <p className="text-amber-300">Substitute assignment</p>}
    {!item.cancelled&&item.can_start&&<div className="mt-4">{pendingStart?.routineId===item.routine_id?<div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold text-emerald-100">Location captured</p><Badge tone="success">+/-{Math.round(pendingStart?.accuracy ?? 0)}m accuracy</Badge></div><label className="mt-4 block"><span className="field-label">Attendance boundary (meters)</span><input className="w-full" type="number" min="1" step="1" inputMode="decimal" value={radiusInput} onChange={(event)=>setRadiusInput(event.target.value)} aria-describedby={`boundary-help-${item.routine_id}`}/><span id={`boundary-help-${item.routine_id}`} className="helper-text">Students farther than this distance from your captured location will be sent to you for manual verification.</span></label><div className="mt-4 flex flex-wrap gap-2"><Button size="lg" loading={startingId===item.routine_id} disabled={startingId!==null} onClick={()=>void startSession()}>{startingId===item.routine_id?"Starting QR session…":"Start QR attendance"}</Button><Button type="button" variant="ghost" disabled={startingId!==null} onClick={()=>{setPendingStart(null);setStartStatus("")}}>Cancel</Button></div></div>:<Button size="lg" loading={startingId===item.routine_id} disabled={startingId!==null||pendingStart!==null} onClick={()=>void start(item.routine_id)}>{startingId===item.routine_id?"Getting location…":"Use location & set boundary"}</Button>}</div>}
  </article>;

  return <div>
    <PageHeader title="My classes" description="Filter your teaching schedule, then start today’s attendance session from the classroom."/>
    <section className="panel mb-6 p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Schedule filters</h2><p className="mt-1 text-sm text-slate-400">Filters apply to today, your next class, and the full timetable.</p></div><Button type="button" variant="ghost" onClick={() => setFilters({ query: "", module: "", section: "", classType: "", day: "" })}>Clear filters</Button></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label><span className="field-label">Search</span><input placeholder="Course, section, or room" value={filters.query} onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))} /></label>
        <label><span className="field-label">Module</span><select value={filters.module} onChange={(event) => setFilters((current) => ({ ...current, module: event.target.value }))}><option value="">All modules</option>{(data.modules || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.code} — {entry.title}</option>)}</select></label>
        <label><span className="field-label">Section</span><input placeholder="Any section" value={filters.section} onChange={(event) => setFilters((current) => ({ ...current, section: event.target.value }))} /></label>
        <label><span className="field-label">Class type</span><select value={filters.classType} onChange={(event) => setFilters((current) => ({ ...current, classType: event.target.value }))}><option value="">All class types</option>{(data["class-types"] || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
        <label><span className="field-label">Timetable day</span><select value={filters.day} onChange={(event) => setFilters((current) => ({ ...current, day: event.target.value }))}><option value="">All days</option>{days.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
      </div>
    </section>
    {startStatus && <p className="mb-3 rounded border border-emerald-800 bg-emerald-950/30 p-3 text-emerald-300">{startStatus}</p>}
    {error&&<div className="mb-4"><ErrorState title="Unable to continue" description={error} onRetry={()=>locationRetryRoutineId!==null?void start(locationRetryRoutineId):void load()}/></div>}
    {loading?<LoadingState label="Loading teaching schedule"/>:<><section><h2 className="mb-3 text-lg font-semibold">Today&apos;s classes</h2><div className="grid gap-4 md:grid-cols-2">{today.map(occurrenceCard)}{!today.length&&<div className="panel md:col-span-2"><EmptyState title="No classes scheduled today" description="Your next scheduled class will appear below."/></div>}</div></section>
    <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">Next Class</h2>{next ? <div><p className="mb-2 text-slate-400">{next.date}</p>{occurrenceCard(next)}</div> : <p className="text-slate-400">No upcoming class.</p>}</section>
    <section className="mt-8"><h2 className="mb-3 text-lg font-semibold">Full timetable</h2><RoutineScheduleCards rows={filteredRows} colorRows={rows} days={days} colorBy="room_id" colorMeaning="Classroom" time={(row) => text("time-slots", row.time_slot_id)} title={(row) => text("modules", row.module_id)} classType={(row) => text("class-types", row.class_type_id)} details={(row) => [{ label: "Sections", value: row.section_names?.join(" + ") || "Not assigned" }, { label: "Room", value: text("rooms", row.room_id) }]} /></section></>}
  </div>;
}
