"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/States";
import { apiMessage, AvailabilityState, ScheduleFeedback } from "@/components/ScheduleFeedback";

const empty = {override_date:"",new_teacher_id:"",new_room:"",start_time:"",end_time:"",is_cancelled:false,reason:""};
const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Page() {
  const params = useSearchParams();
  const [data, setData] = useState<Record<string, any[]>>({});
  const [routineId, setRoutineId] = useState(params.get("routine_id") || "");
  const [rows, setRows] = useState<any[]>([]);
  const [form, setForm] = useState<any>(empty);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [decision, setDecision] = useState<{id:number;status:"approved"|"rejected"}|null>(null);
  const [availability, setAvailability] = useState<AvailabilityState>({ status: "incomplete", message: "Select a class and date to check the override." });

  useEffect(() => { const names = ["routines","teachers","modules","rooms","blocks","time-slots"]; Promise.all(names.map((name) => api.get(`/api/v1/academic/${name}`))).then((responses) => setData(Object.fromEntries(names.map((name,index) => [name,responses[index].data])))).catch((requestError) => setError(apiMessage(requestError, "Unable to load overrides."))); }, []);
  async function load(id = routineId) { if (id) setRows((await api.get(`/api/v1/academic/routines/${id}/overrides`)).data); else setRows([]); }
  useEffect(() => { if (routineId) api.get(`/api/v1/academic/routines/${routineId}/overrides`).then((response) => setRows(response.data)).catch((requestError) => setError(apiMessage(requestError, "Unable to load overrides."))); else setRows([]); }, [routineId]);

  const find = (kind:string,id:number) => data[kind]?.find((item) => item.id === id);
  const routineLabel = (routine:any) => {
    // `module` is legacy display-variable naming; it is not the CommonJS global.
    // eslint-disable-next-line @next/next/no-assign-module-variable
    const module = find("modules", routine.module_id), slot = find("time-slots", routine.time_slot_id), room = find("rooms", routine.room_id), block = room && find("blocks", room.block_id);
    return `${days[routine.day_of_week]} · ${slot ? `${slot.start_time.slice(0,5)}–${slot.end_time.slice(0,5)}` : "Time not assigned"} · ${module ? `${module.code} — ${module.title}` : "Module not assigned"} · ${routine.section_names?.join(" + ") || "Section not assigned"} · ${[block?.name,room?.name].filter(Boolean).join("-") || "Room not assigned"}`;
  };

  const overridePayload = useMemo(() => ({...form,new_teacher_id:form.new_teacher_id ? Number(form.new_teacher_id) : null,new_room:form.new_room || null,start_time:form.start_time || null,end_time:form.end_time || null}), [form]);

  useEffect(() => {
    if (!routineId || !form.override_date) {
      setAvailability({ status: "incomplete", message: "Select a class and date to check the override." });
      return;
    }
    const controller = new AbortController();
    setAvailability({ status: "checking", message: "Checking the effective schedule for this date…" });
    api.post(`/api/v1/academic/routines/${routineId}/overrides/availability`, overridePayload, { signal: controller.signal })
      .then((response) => setAvailability(response.data.available ? { status: "available", message: form.is_cancelled ? "This class will be cancelled; no resource conflict is created." : "The selected override does not conflict with another class." } : { status: "conflict", conflicts: response.data.conflicts, message: "This override overlaps a class already scheduled on that date." }))
      .catch((requestError) => {
        if (!controller.signal.aborted) setAvailability({ status: "error", message: apiMessage(requestError, "The override could not be checked.") });
      });
    return () => controller.abort();
  }, [routineId, form.override_date, form.is_cancelled, overridePayload]);

  async function submit(event:FormEvent) {
    event.preventDefault();
    if (availability.status === "conflict") { setError("This override cannot be saved until the lecturer, room, section, or time conflict in System feedback is resolved."); return; }
    setSaving(true);
    try { await api.post(`/api/v1/academic/routines/${routineId}/overrides`, overridePayload); setForm(empty); setError(""); await load(); }
    catch (requestError:any) { setError(apiMessage(requestError, "Unable to create override.")); }
    finally { setSaving(false); }
  }
  async function decide() { if (!decision) return; setSaving(true); try { await api.patch(`/api/v1/academic/routines/${routineId}/overrides/${decision.id}`, {status:decision.status}); setDecision(null); setError(""); await load(); } catch (requestError:any) { setError(apiMessage(requestError, "Unable to update this override.")); } finally { setSaving(false); } }

  const selected = data.routines?.find((routine) => routine.id === Number(routineId));
  return <div className="max-w-6xl">
    <PageHeader title="Routine overrides" description="Schedule a substitute, room or time change, or cancellation for a specific class date." />
    <label><span className="field-label">Routine entry</span><select className="w-full" value={routineId} onChange={(event) => setRoutineId(event.target.value)}><option value="">Select a class</option>{(data.routines || []).map((routine) => <option key={routine.id} value={routine.id}>{routineLabel(routine)}</option>)}</select></label>
    {selected && <div className="mt-4 rounded-xl border border-blue-500/20 bg-blue-500/5 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-blue-300">Original class</p><p className="mt-1 text-sm text-slate-200">{routineLabel(selected)}</p></div>}
    {routineId && <form onSubmit={submit} className="mt-5 grid gap-4 panel p-5 md:grid-cols-2">
      <label><span className="field-label">Override date</span><input className="w-full" required type="date" value={form.override_date} onChange={(event) => setForm({...form,override_date:event.target.value})} /></label>
      <label><span className="field-label">Substitute lecturer</span><select className="w-full" value={form.new_teacher_id} onChange={(event) => setForm({...form,new_teacher_id:event.target.value})}><option value="">Keep original lecturer</option>{(data.teachers || []).map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.name}</option>)}</select></label>
      <label><span className="field-label">New room</span><input list="override-rooms" className="w-full" value={form.new_room} onChange={(event) => setForm({...form,new_room:event.target.value})} placeholder="Keep original room" /><datalist id="override-rooms">{(data.rooms || []).map((room) => <option key={room.id} value={room.name}/>)}</datalist></label>
      <label className="flex min-h-10 items-center gap-2 self-end"><input type="checkbox" checked={form.is_cancelled} onChange={(event) => setForm({...form,is_cancelled:event.target.checked})} /><span className="text-sm font-medium text-slate-200">Cancel this class</span></label>
      <label><span className="field-label">New start time</span><input className="w-full" type="time" value={form.start_time} onChange={(event) => setForm({...form,start_time:event.target.value})} /></label>
      <label><span className="field-label">New end time</span><input className="w-full" type="time" value={form.end_time} onChange={(event) => setForm({...form,end_time:event.target.value})} /></label>
      <label className="md:col-span-2"><span className="field-label">Reason</span><textarea className="min-h-24 w-full" required value={form.reason} onChange={(event) => setForm({...form,reason:event.target.value})} placeholder="Explain why this change is needed" /></label>
      <div className="md:col-span-2"><p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-slate-400">System feedback</p><ScheduleFeedback state={availability} /></div>
      <div className="md:col-span-2"><Button loading={saving}>{saving ? "Creating…" : "Create override"}</Button></div>
    </form>}
    {error && <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200" role="alert">{error}</p>}
    <section className="mt-8"><h2 className="text-lg font-semibold">Override history</h2><div className="mt-4 space-y-3">{routineId && !rows.length ? <EmptyState title="No overrides for this class" description="Dated schedule changes will appear here." /> : rows.map((row) => <article key={row.id} className="panel flex flex-col gap-4 p-4 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-100">{new Date(`${row.override_date}T00:00:00`).toLocaleDateString(undefined,{dateStyle:"medium"})}</p><StatusBadge status={row.status} />{row.is_cancelled && <StatusBadge status="cancelled" />}</div><p className="mt-2 text-sm text-slate-300">{row.is_cancelled ? "Class cancelled" : row.new_teacher_id ? `Substitute: ${find("teachers",row.new_teacher_id)?.name || "Assigned lecturer"}` : row.new_room ? `Room: ${row.new_room}` : "Time adjusted"}</p><p className="mt-1 text-sm text-slate-500">{row.reason}</p></div>{row.status === "pending" && <div className="flex gap-2"><Button size="sm" onClick={() => setDecision({id:row.id,status:"approved"})}>Approve</Button><Button variant="danger" size="sm" onClick={() => setDecision({id:row.id,status:"rejected"})}>Reject</Button></div>}</article>)}</div></section>
    <ConfirmDialog open={Boolean(decision)} title={`${decision?.status === "approved" ? "Approve" : "Reject"} this override?`} description="This decision will update the effective schedule and be visible to affected users." confirmLabel={decision?.status === "approved" ? "Approve override" : "Reject override"} tone={decision?.status === "approved" ? "primary" : "danger"} onClose={() => setDecision(null)} onConfirm={decide} />
  </div>;
}
