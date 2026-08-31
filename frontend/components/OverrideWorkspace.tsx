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

const empty = { override_date: "", teacher_id: "", room_id: "", start_time: "", end_time: "", is_cancelled: false, reason: "" };
const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type Routine = { id: number; intake_id: number; semester_number: number; section_id: number; section_names: string[]; module_id: number; class_type_id: number; teacher_id: number; room_id: number; day_of_week: number; time_slot_id: number };

function timeValue(value?: string) {
  return value?.slice(0, 5) || "";
}

function initialForm(routine: Routine, slots: any[]) {
  const slot = slots.find((item) => item.id === routine.time_slot_id);
  return { ...empty, teacher_id: String(routine.teacher_id), room_id: String(routine.room_id), start_time: timeValue(slot?.start_time), end_time: timeValue(slot?.end_time) };
}

export default function OverrideWorkspace() {
  const params = useSearchParams();
  const [data, setData] = useState<Record<string, any[]>>({});
  const [intakeId, setIntakeId] = useState(params.get("intake_id") || "");
  const [routineId, setRoutineId] = useState(params.get("routine_id") || "");
  const [rows, setRows] = useState<any[]>([]);
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [decision, setDecision] = useState<{ id: number; status: "approved" | "rejected" } | null>(null);
  const [availability, setAvailability] = useState<AvailabilityState>({ status: "incomplete", message: "Select a class and date to check the override." });

  useEffect(() => {
    const names = ["routines", "intakes", "teachers", "modules", "rooms", "blocks", "time-slots"];
    Promise.all(names.map((name) => api.get(`/api/v1/academic/${name}`)))
      .then((responses) => setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data]))))
      .catch((requestError) => setError(apiMessage(requestError, "Unable to load overrides.")));
  }, []);

  const find = (kind: string, id: number) => data[kind]?.find((item) => item.id === id);
  const roomLabel = (room: any) => room ? [find("blocks", room.block_id)?.name, room.name].filter(Boolean).join(" / ") : "Room not assigned";
  const routineLabel = (routine: Routine) => {
    const academicModule = find("modules", routine.module_id);
    const slot = find("time-slots", routine.time_slot_id);
    return `${days[routine.day_of_week]} | ${slot ? `${timeValue(slot.start_time)}-${timeValue(slot.end_time)}` : "Time not assigned"} | ${academicModule ? `${academicModule.code} - ${academicModule.title}` : "Module not assigned"} | ${routine.section_names?.join(" + ") || "Section not assigned"} | ${roomLabel(find("rooms", routine.room_id))}`;
  };

  const selected = useMemo(() => (data.routines || []).find((routine) => routine.id === Number(routineId)) as Routine | undefined, [data.routines, routineId]);
  const routineOptions = useMemo(() => (data.routines || []).filter((routine) => !intakeId || routine.intake_id === Number(intakeId)) as Routine[], [data.routines, intakeId]);
  const selectedSlot = selected ? find("time-slots", selected.time_slot_id) : undefined;

  useEffect(() => {
    if (routineId && selected && !intakeId) setIntakeId(String(selected.intake_id));
  }, [intakeId, routineId, selected]);

  useEffect(() => {
    setForm(selected ? initialForm(selected, data["time-slots"] || []) : empty);
    setError("");
    setAvailability({ status: "incomplete", message: "Select a class and date to check the override." });
  }, [data, selected?.id]);

  async function load(id = routineId) {
    if (!id) {
      setRows([]);
      return;
    }
    try {
      setRows((await api.get(`/api/v1/academic/routines/${id}/overrides`)).data);
    } catch (requestError) {
      setError(apiMessage(requestError, "Unable to load overrides."));
    }
  }

  useEffect(() => { void load(); }, [routineId]);

  const overridePayload = useMemo(() => ({
    override_date: form.override_date,
    new_teacher_id: selected && form.teacher_id && Number(form.teacher_id) !== selected.teacher_id ? Number(form.teacher_id) : null,
    new_room_id: selected && form.room_id && Number(form.room_id) !== selected.room_id ? Number(form.room_id) : null,
    start_time: selectedSlot && form.start_time !== timeValue(selectedSlot.start_time) ? form.start_time || null : null,
    end_time: selectedSlot && form.end_time !== timeValue(selectedSlot.end_time) ? form.end_time || null : null,
    is_cancelled: form.is_cancelled,
    reason: form.reason,
  }), [form, selected, selectedSlot]);

  useEffect(() => {
    if (!routineId || !selected || !form.override_date) {
      setAvailability({ status: "incomplete", message: "Select a class and date to check the override." });
      return;
    }
    const controller = new AbortController();
    setAvailability({ status: "checking", message: "Checking the effective schedule for this date..." });
    api.post(`/api/v1/academic/routines/${routineId}/overrides/availability`, overridePayload, { signal: controller.signal })
      .then((response) => setAvailability(response.data.available ? { status: "available", message: form.is_cancelled ? "This class will be cancelled; no resource conflict is created." : "The selected override does not conflict with another class." } : { status: "conflict", conflicts: response.data.conflicts, message: "This override overlaps a class already scheduled on that date." }))
      .catch((requestError) => {
        if (!controller.signal.aborted) setAvailability({ status: "error", message: apiMessage(requestError, "The override could not be checked.") });
      });
    return () => controller.abort();
  }, [form.is_cancelled, form.override_date, overridePayload, routineId, selected]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || availability.status === "conflict") {
      setError("This override cannot be saved until the lecturer, room, section, or time conflict in System feedback is resolved.");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/api/v1/academic/routines/${routineId}/overrides`, overridePayload);
      setForm(initialForm(selected, data["time-slots"] || []));
      setError("");
      await load();
    } catch (requestError) {
      setError(apiMessage(requestError, "Unable to create override."));
    } finally {
      setSaving(false);
    }
  }

  async function decide() {
    if (!decision) return;
    setSaving(true);
    try {
      await api.patch(`/api/v1/academic/routines/${routineId}/overrides/${decision.id}`, { status: decision.status });
      setDecision(null);
      setError("");
      await load();
    } catch (requestError) {
      setError(apiMessage(requestError, "Unable to update this override."));
    } finally {
      setSaving(false);
    }
  }

  const historySummary = (row: any) => {
    if (row.is_cancelled) return "Class cancelled";
    const changes = [];
    if (row.new_teacher_id) changes.push(`Lecturer: ${find("teachers", row.new_teacher_id)?.name || "Assigned lecturer"}`);
    if (row.new_room_id) changes.push(`Room: ${roomLabel(find("rooms", row.new_room_id))}`);
    else if (row.new_room) changes.push(`Room: ${row.new_room}`);
    if (row.start_time || row.end_time) changes.push(`Time: ${timeValue(row.start_time) || timeValue(selectedSlot?.start_time)}-${timeValue(row.end_time) || timeValue(selectedSlot?.end_time)}`);
    return changes.join(" / ") || "Class details retained";
  };

  return <div className="max-w-6xl">
    <PageHeader title="Routine overrides" description="Schedule a lecturer, room or time change, or cancellation for a specific class date." />
    <div className="grid gap-4 sm:grid-cols-2">
      <label><span className="field-label">Intake</span><select className="w-full" value={intakeId} onChange={(event) => { setIntakeId(event.target.value); setRoutineId(""); }}><option value="">All intakes</option>{(data.intakes || []).map((intake) => <option key={intake.id} value={intake.id}>{intake.code} - {intake.name}</option>)}</select></label>
      <label><span className="field-label">Routine entry</span><select className="w-full" value={routineId} onChange={(event) => setRoutineId(event.target.value)}><option value="">Select a class</option>{routineOptions.map((routine) => <option key={routine.id} value={routine.id}>{routineLabel(routine)}</option>)}</select></label>
    </div>
    {selected && <div className="mt-4 rounded-xl border border-blue-500/20 bg-blue-500/5 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-blue-300">Original class</p><p className="mt-1 text-sm text-slate-200">{routineLabel(selected)}</p><p className="mt-2 text-sm text-slate-400">The lecturer, room, and time fields below begin with these current values. Change only what is needed.</p></div>}
    {selected && <form onSubmit={submit} className="mt-5 grid gap-4 panel p-5 md:grid-cols-2">
      <label><span className="field-label">Override date</span><input className="w-full" required type="date" value={form.override_date} onChange={(event) => setForm({ ...form, override_date: event.target.value })} /></label>
      <label><span className="field-label">Lecturer</span><select className="w-full" value={form.teacher_id} onChange={(event) => setForm({ ...form, teacher_id: event.target.value })}>{(data.teachers || []).map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.name}{teacher.id === selected.teacher_id ? " - current class" : ""}</option>)}</select></label>
      <label><span className="field-label">Room</span><select className="w-full" value={form.room_id} onChange={(event) => setForm({ ...form, room_id: event.target.value })}>{(data.rooms || []).map((room) => <option key={room.id} value={room.id}>{roomLabel(room)}{room.id === selected.room_id ? " - current class" : ""}</option>)}</select></label>
      <label className="flex min-h-10 items-center gap-2 self-end"><input type="checkbox" checked={form.is_cancelled} onChange={(event) => setForm({ ...form, is_cancelled: event.target.checked })} /><span className="text-sm font-medium text-slate-200">Cancel this class</span></label>
      <label><span className="field-label">Start time</span><input className="w-full" type="time" value={form.start_time} onChange={(event) => setForm({ ...form, start_time: event.target.value })} /></label>
      <label><span className="field-label">End time</span><input className="w-full" type="time" value={form.end_time} onChange={(event) => setForm({ ...form, end_time: event.target.value })} /></label>
      <label className="md:col-span-2"><span className="field-label">Reason</span><textarea className="min-h-24 w-full" required value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder="Explain why this change is needed" /></label>
      <div className="md:col-span-2"><p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-slate-400">System feedback</p><ScheduleFeedback state={availability} /></div>
      <div className="md:col-span-2"><Button loading={saving} disabled={availability.status === "checking" || availability.status === "conflict"}>{saving ? "Creating..." : "Create override"}</Button></div>
    </form>}
    {error && <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200" role="alert">{error}</p>}
    <section className="mt-8"><h2 className="text-lg font-semibold">Override history</h2><div className="mt-4 space-y-3">{routineId && !rows.length ? <EmptyState title="No overrides for this class" description="Dated schedule changes will appear here." /> : rows.map((row) => <article key={row.id} className="panel flex flex-col gap-4 p-4 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-100">{new Date(`${row.override_date}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })}</p><StatusBadge status={row.status} />{row.is_cancelled && <StatusBadge status="cancelled" />}</div><p className="mt-2 text-sm text-slate-300">{historySummary(row)}</p><p className="mt-1 text-sm text-slate-500">{row.reason}</p></div>{row.status === "pending" && <div className="flex gap-2"><Button size="sm" onClick={() => setDecision({ id: row.id, status: "approved" })}>Approve</Button><Button variant="danger" size="sm" onClick={() => setDecision({ id: row.id, status: "rejected" })}>Reject</Button></div>}</article>)}</div></section>
    <ConfirmDialog open={Boolean(decision)} title={`${decision?.status === "approved" ? "Approve" : "Reject"} this override?`} description="This decision will update the effective schedule and be visible to affected users." confirmLabel={decision?.status === "approved" ? "Approve override" : "Reject override"} tone={decision?.status === "approved" ? "primary" : "danger"} onClose={() => setDecision(null)} onConfirm={decide} />
  </div>;
}
