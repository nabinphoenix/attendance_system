"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { getBestFreshPosition, hasSecureDeviceContext, locationFailureReason } from "@/lib/geolocation";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

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
  const [radiusInput, setRadiusInput] = useState("150");

  async function load() {
    setError("");
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

  const find = (key: string, id: number) => data[key]?.find((item) => item.id === id);
  const text = (key: string, id: number) => {
    const item = find(key, id);
    if (!item) return String(id);
    if (key === "modules") return `${item.code} — ${item.title}`;
    if (key === "time-slots") return `${item.start_time?.slice(0, 5)}–${item.end_time?.slice(0, 5)}`;
    if (key === "rooms") return `${find("blocks", item.block_id)?.name ?? ""} / ${item.name}`;
    return item.name || item.code;
  };

  async function start(routineId: number) {
    if (!hasSecureDeviceContext()) {
      setError("Starting a QR attendance session requires a secure HTTPS connection so the browser can share your classroom location.");
      return;
    }
    setStartingId(routineId);
    setError("");
    setStartStatus("Getting your classroom location…");
    try {
      const position = await getBestFreshPosition();
      setPendingStart({ routineId, latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy });
      setStartStatus(`Location captured with +/-${Math.round(position.coords.accuracy)}m accuracy. Choose the attendance boundary, then start the QR session.`);
      setStartingId(null);
      return;
    } catch (requestError: any) {
      const detail = requestError.response?.data?.detail;
      if (detail) setError(detail);
      else {
        const reason = locationFailureReason(requestError);
        setError(reason === "LOCATION_DENIED"
          ? "Location permission is required to create the classroom geofence. Allow location access and retry."
          : reason === "LOCATION_TIMEOUT"
            ? "A fresh classroom location could not be obtained in time. Move near a window and retry."
            : "Classroom location is unavailable on this device. Check location services and retry.");
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
      setError(requestError.response?.data?.detail ?? "Unable to start this attendance session.");
      setStartStatus("");
      setStartingId(null);
    }
  }

  const today = occurrences.filter((item) => item.date === localDate());
  const next = occurrences.find((item) => !item.cancelled);
  const occurrenceCard = (item: any) => <article key={`${item.routine_id}-${item.date}`} className={`panel p-5 ${item.cancelled ? "border-red-500/40 bg-red-500/5" : ""}`}>
    <div className="flex items-start justify-between gap-3"><p className="text-lg font-semibold text-slate-100">{item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</p><Badge tone={item.cancelled?"danger":"info"}>{item.cancelled?"Cancelled":text("class-types", item.class_type_id)}</Badge></div>
    <h3 className="mt-3 text-lg font-semibold">{text("modules", item.module_id)}</h3>
    <p className="mt-2 text-sm text-slate-300">{item.section_names.join(" + ")} · {item.room}</p>
    {item.room !== item.original_room && <p className="text-amber-300">Original room: {item.original_room} · Effective room: {item.room}</p>}
    {item.teacher_id !== item.original_teacher_id && <p className="text-amber-300">Substitute assignment</p>}
    {!item.cancelled&&item.can_start&&<div className="mt-4">{pendingStart?.routineId===item.routine_id?<div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold text-emerald-100">Location captured</p><Badge tone="success">+/-{Math.round(pendingStart?.accuracy ?? 0)}m accuracy</Badge></div><label className="mt-4 block"><span className="field-label">Attendance boundary (meters)</span><input className="w-full" type="number" min="1" step="1" inputMode="decimal" value={radiusInput} onChange={(event)=>setRadiusInput(event.target.value)} aria-describedby={`boundary-help-${item.routine_id}`}/><span id={`boundary-help-${item.routine_id}`} className="helper-text">Students farther than this distance from your captured location will be sent to you for manual verification.</span></label><div className="mt-4 flex flex-wrap gap-2"><Button size="lg" loading={startingId===item.routine_id} disabled={startingId!==null} onClick={()=>void startSession()}>{startingId===item.routine_id?"Starting QR session…":"Start QR attendance"}</Button><Button type="button" variant="ghost" disabled={startingId!==null} onClick={()=>{setPendingStart(null);setStartStatus("")}}>Cancel</Button></div></div>:<Button size="lg" loading={startingId===item.routine_id} disabled={startingId!==null||pendingStart!==null} onClick={()=>void start(item.routine_id)}>{startingId===item.routine_id?"Getting location…":"Use location & set boundary"}</Button>}</div>}
  </article>;

  return <div>
    <PageHeader title="My classes" description="View your teaching schedule and start today’s attendance session from the classroom."/>
    {startStatus && <p className="mb-3 rounded border border-emerald-800 bg-emerald-950/30 p-3 text-emerald-300">{startStatus}</p>}
    {error&&<div className="mb-4"><ErrorState title="Unable to continue" description={error} onRetry={()=>void load()}/></div>}
    {loading?<LoadingState label="Loading teaching schedule"/>:<><section><h2 className="mb-3 text-lg font-semibold">Today&apos;s classes</h2><div className="grid gap-4 md:grid-cols-2">{today.map(occurrenceCard)}{!today.length&&<div className="panel md:col-span-2"><EmptyState title="No classes scheduled today" description="Your next scheduled class will appear below."/></div>}</div></section>
    <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">Next Class</h2>{next ? <div><p className="mb-2 text-slate-400">{next.date}</p>{occurrenceCard(next)}</div> : <p className="text-slate-400">No upcoming class.</p>}</section>
    <section className="mt-8"><h2 className="mb-3 text-lg font-semibold">Full timetable</h2><div className="table-wrap"><table><thead><tr><th>Day &amp; time</th><th>Module</th><th>Type</th><th>Sections</th><th>Room</th></tr></thead><tbody>{[...rows].sort((a,b)=>a.day_of_week-b.day_of_week).map(row=><tr key={row.id}><td><b className="text-slate-200">{days[row.day_of_week]}</b><br/><span className="text-slate-400">{text("time-slots",row.time_slot_id)}</span></td><td>{text("modules",row.module_id)}</td><td><Badge>{text("class-types",row.class_type_id)}</Badge></td><td>{row.section_names?.join(" + ")}</td><td>{text("rooms",row.room_id)}</td></tr>)}</tbody></table></div></section></>}
  </div>;
}
