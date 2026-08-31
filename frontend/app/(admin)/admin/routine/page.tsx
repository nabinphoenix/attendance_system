"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { HorizontalPagination } from "@/components/ui/HorizontalPagination";
import SectionRoutineImportPanel from "@/components/SectionRoutineImportPanel";
import { apiMessage, AvailabilityState, ScheduleFeedback } from "@/components/ScheduleFeedback";
import RoomAvailabilityPanel from "@/components/RoomAvailabilityPanel";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const blank = { intake_id: "", semester_number: "", module_id: "", class_type_id: "", teacher_id: "", room_id: "", time_slot_id: "", day_of_week: "0", block_id: "" };
const emptyFilters = { intake: "", semester: "", section: "", teacher: "", module: "", day: "", room: "", block: "" };
const queryKeys: Record<string, string> = { intake: "intake_id", semester: "semester_number", section: "section_id", teacher: "teacher_id", module: "module_id", day: "day_of_week", room: "room_id", block: "block_id" };

type Workspace = "schedule" | "create" | "import" | "availability";
type Routine = { id: number; intake_id: number; semester_number: number; section_id: number; section_ids: number[]; section_names: string[]; module_id: number; class_type_id: number; teacher_id: number; room_id: number; day_of_week: number; time_slot_id: number };
type RoutinePage = { items: Routine[]; total: number; page: number; page_size: number };

export default function Page() {
  const [data, setData] = useState<Record<string, any[]>>({});
  const [routinePage, setRoutinePage] = useState<RoutinePage>({ items: [], total: 0, page: 1, page_size: 10 });
  const [workspace, setWorkspace] = useState<Workspace>("schedule");
  const [form, setForm] = useState<Record<string, string>>(blank);
  const [sectionIds, setSectionIds] = useState<number[]>([]);
  const [sectionPicker, setSectionPicker] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [error, setError] = useState("");
  const [masterLoading, setMasterLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [availability, setAvailability] = useState<AvailabilityState>({ status: "incomplete" });

  async function loadMasterData() {
    setMasterLoading(true);
    try {
      const names = ["intakes", "sections", "modules", "module-offerings", "class-types", "teachers", "rooms", "blocks", "time-slots"];
      const responses = await Promise.all(names.map((name) => api.get(`/api/v1/academic/${name}`)));
      setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data])));
      setError("");
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Unable to load routine setup data."));
    } finally {
      setMasterLoading(false);
    }
  }

  async function loadRoutinePage(requestedPage = page) {
    setTableLoading(true);
    try {
      const params = new URLSearchParams({ page: String(requestedPage), page_size: String(pageSize) });
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(queryKeys[key], value);
      });
      const response = await api.get(`/api/v1/academic/routines/page?${params}`);
      setRoutinePage(response.data);
      setError("");
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Unable to load the published routine."));
    } finally {
      setTableLoading(false);
    }
  }

  useEffect(() => { void loadMasterData(); }, []);
  useEffect(() => { void loadRoutinePage(); }, [page, pageSize, filters]);

  const item = (kind: string, id: number) => data[kind]?.find((entry) => entry.id === id);
  const label = (kind: string, id: number) => {
    const entry = item(kind, id);
    if (!entry) return "Not assigned";
    if (kind === "modules") return `${entry.code} — ${entry.title}`;
    if (kind === "teachers") return entry.name;
    if (kind === "rooms") return [item("blocks", entry.block_id)?.name, entry.name].filter(Boolean).join(" / ");
    if (kind === "time-slots") return `${entry.start_time?.slice(0, 5)}–${entry.end_time?.slice(0, 5)}`;
    return entry.name || entry.code;
  };
  const sections = useMemo(() => (data.sections || []).filter((entry) =>
    (!form.intake_id || entry.intake_id === null || entry.intake_id === Number(form.intake_id)) &&
    (!form.semester_number || entry.semester_number === null || entry.semester_number === Number(form.semester_number)),
  ), [data.sections, form.intake_id, form.semester_number]);
  const offerings = useMemo(() => (data["module-offerings"] || []).filter((entry) =>
    entry.is_active && entry.intake_id === Number(form.intake_id) && entry.semester_number === Number(form.semester_number) && sectionIds.length > 0 && sectionIds.every((id) => entry.section_ids.includes(id)),
  ), [data, form.intake_id, form.semester_number, sectionIds]);
  const rooms = useMemo(() => (data.rooms || []).filter((entry) => !form.block_id || entry.block_id === Number(form.block_id)), [data.rooms, form.block_id]);

  function setAcademic(key: string, value: string) {
    setForm((current) => ({ ...current, [key]: value, module_id: "" }));
    setSectionIds([]);
    setSectionPicker("");
  }
  function addSection(sectionId: string) {
    if (!sectionId) return;
    const id = Number(sectionId);
    setSectionIds((current) => current.includes(id) ? current : [...current, id]);
    setSectionPicker("");
  }
  function changeFilter(key: string, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }
  const routinePayload = useMemo(() => ({ intake_id: Number(form.intake_id), semester_number: Number(form.semester_number), section_id: sectionIds[0], section_ids: sectionIds, module_id: Number(form.module_id), class_type_id: Number(form.class_type_id), teacher_id: Number(form.teacher_id), room_id: Number(form.room_id), time_slot_id: Number(form.time_slot_id), day_of_week: Number(form.day_of_week) }), [form, sectionIds]);
  const formComplete = useMemo(() => Boolean(form.intake_id && form.semester_number && form.module_id && form.class_type_id && form.teacher_id && form.room_id && form.time_slot_id && sectionIds.length), [form, sectionIds]);

  useEffect(() => {
    if (workspace !== "create" || !formComplete) {
      setAvailability({ status: "incomplete" });
      return;
    }
    const controller = new AbortController();
    setAvailability({ status: "checking" });
    api.post("/api/v1/academic/routines/availability", routinePayload, { signal: controller.signal })
      .then((response) => setAvailability(response.data.available ? { status: "available" } : { status: "conflict", conflicts: response.data.conflicts, message: "The selected time overlaps a class already in the routine." }))
      .catch((requestError) => {
        if (!controller.signal.aborted) setAvailability({ status: "error", message: apiMessage(requestError, "Complete the class setup before checking availability.") });
      });
    return () => controller.abort();
  }, [workspace, formComplete, routinePayload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!sectionIds.length) { setError("Select at least one section."); return; }
    if (availability.status === "conflict") { setError("This time is unavailable. Change the lecturer, room, section, or time slot shown in System feedback."); return; }
    setSaving(true);
    try {
      await api.post("/api/v1/academic/routines", routinePayload);
      setForm(blank); setSectionIds([]); setSectionPicker(""); setError(""); setWorkspace("schedule"); setPage(1); await loadRoutinePage(1);
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Unable to create routine entry."));
    } finally {
      setSaving(false);
    }
  }
  const formSelect = (key: string, title: string, kind: string, items = data[kind] || []) => <label><span className="field-label">{title}</span><select className="w-full" required value={form[key]} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}><option value="">Select {title.toLowerCase()}</option>{items.map((entry: any) => <option key={entry.id} value={entry.id}>{label(kind, entry.id)}</option>)}</select></label>;
  const filterSelect = (key: string, title: string, kind: string) => <label><span className="field-label">{title}</span><select className="w-full" value={filters[key]} onChange={(event) => changeFilter(key, event.target.value)}><option value="">All {title.toLowerCase()}s</option>{(data[kind] || []).map((entry) => <option key={entry.id} value={entry.id}>{label(kind, entry.id)}</option>)}</select></label>;

  return <div className="max-w-7xl">
    <PageHeader title="Routine planner" description="Create, import, review, and resolve the recurring timetable from one focused workspace." action={<div className="flex flex-wrap gap-2"><Button type="button" variant={workspace === "schedule" ? "primary" : "outline"} size="sm" onClick={() => setWorkspace("schedule")}>Published routine</Button><Button type="button" variant={workspace === "create" ? "primary" : "outline"} size="sm" onClick={() => setWorkspace("create")}>Add class</Button><Button type="button" variant={workspace === "import" ? "primary" : "outline"} size="sm" onClick={() => setWorkspace("import")}>Import sheet</Button></div>} />
    <div className="mb-5 flex justify-end"><Button type="button" variant={workspace === "availability" ? "primary" : "outline"} size="sm" onClick={() => setWorkspace("availability")}>Room availability</Button></div>
    {error && <div className="mb-5"><ErrorState title="Routine workspace needs attention" description={error} onRetry={() => { void loadMasterData(); void loadRoutinePage(); }} /></div>}

    {workspace === "create" && <section className="panel p-5 sm:p-6"><div className="mb-6 flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">Add a recurring class</h2><p className="mt-1 text-sm text-slate-400">The system checks lecturer, room, section, and active offering conflicts before saving.</p></div><Badge tone="info">Conflict checked</Badge></div><form onSubmit={submit} className="grid gap-4 md:grid-cols-3">
      <label><span className="field-label">Intake</span><select className="w-full" required value={form.intake_id} onChange={(event) => setAcademic("intake_id", event.target.value)}><option value="">Select intake</option>{(data.intakes || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.code} — {entry.name}</option>)}</select></label>
      <label><span className="field-label">Semester</span><input className="w-full" required type="number" min="1" value={form.semester_number} onChange={(event) => setAcademic("semester_number", event.target.value)} /></label>
      <div><span className="field-label">Section</span><select className="w-full" value={sectionPicker} onChange={(event) => addSection(event.target.value)} disabled={!form.intake_id || !form.semester_number}><option value="">{form.intake_id && form.semester_number ? "Select section" : "Select intake and semester first"}</option>{sections.filter((entry) => !sectionIds.includes(entry.id)).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select>{Boolean(form.intake_id && form.semester_number && !sections.length) && <span className="mt-1 block text-sm text-amber-300">No sections are configured for this intake and semester.</span>}{sectionIds.length > 0 && <span className="mt-2 flex flex-wrap gap-2">{sectionIds.map((id) => <button key={id} type="button" className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-200" onClick={() => setSectionIds((current) => current.filter((currentId) => currentId !== id))}>{label("sections", id)} <span aria-hidden="true">×</span><span className="sr-only">Remove {label("sections", id)}</span></button>)}</span>}<span className="mt-1 block text-sm text-slate-400">Choose each participating section from the list. Select a chip to remove it.</span></div>
      <label><span className="field-label">Module</span><select className="w-full" required value={form.module_id} onChange={(event) => setForm((current) => ({ ...current, module_id: event.target.value }))}><option value="">Select offered module</option>{offerings.map((entry) => <option key={entry.id} value={entry.academic_module_id}>{entry.module_code} — {entry.module_title}</option>)}</select>{form.intake_id && form.semester_number && sectionIds.length > 0 && !offerings.length && <span className="mt-1 block text-sm text-amber-300">No active offering covers these sections. <Link className="interactive-link underline" href="/admin/academic/module-offerings">Update module offerings</Link>.</span>}</label>
      {formSelect("class_type_id", "Class type", "class-types")}{formSelect("teacher_id", "Lecturer", "teachers")}
      <label><span className="field-label">Day</span><select className="w-full" value={form.day_of_week} onChange={(event) => setForm((current) => ({ ...current, day_of_week: event.target.value }))}>{days.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
      {formSelect("time_slot_id", "Time", "time-slots")}{formSelect("block_id", "Block", "blocks")}{formSelect("room_id", "Room", "rooms", rooms)}
      <div className="md:col-span-3"><p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-slate-400">System feedback</p><ScheduleFeedback state={availability} /></div>
      <div className="flex flex-wrap items-end gap-3 md:col-span-3"><Button loading={saving} disabled={availability.status === "checking" || availability.status === "conflict"}>{saving ? "Saving class…" : "Save recurring class"}</Button><Button type="button" variant="ghost" onClick={() => { setForm(blank); setSectionIds([]); setSectionPicker(""); }}>Clear</Button></div>
    </form></section>}

    {workspace === "import" && <SectionRoutineImportPanel />}
    {workspace === "availability" && <RoomAvailabilityPanel blocks={data.blocks || []} />}

    {workspace === "schedule" && <section className="panel overflow-hidden"><div className="border-b border-slate-800 px-5 py-5 sm:px-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold">Published timetable</h2><Badge tone="success">{routinePage.total} classes</Badge></div><p className="mt-1 text-sm text-slate-400">Filter the schedule, then move through results without loading the full routine into the browser.</p></div><label className="text-sm text-slate-300">Rows per page<select className="ml-2 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{filterSelect("intake", "Intake", "intakes")}{filterSelect("section", "Section", "sections")}{filterSelect("teacher", "Lecturer", "teachers")}{filterSelect("module", "Module", "modules")}<label><span className="field-label">Semester number</span><input className="w-full" type="number" min="1" placeholder="All semesters" value={filters.semester} onChange={(event) => changeFilter("semester", event.target.value)} /></label>{filterSelect("room", "Room", "rooms")}{filterSelect("block", "Block", "blocks")}<label><span className="field-label">Day</span><select className="w-full" value={filters.day} onChange={(event) => changeFilter("day", event.target.value)}><option value="">All days</option>{days.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label><div className="flex items-end"><Button type="button" variant="ghost" onClick={() => { setFilters(emptyFilters); setPage(1); }}>Clear filters</Button></div></div>
    </div>
    {masterLoading || tableLoading ? <div className="p-6"><LoadingState label="Loading published timetable…" /></div> : routinePage.items.length === 0 ? <div className="p-6"><EmptyState title="No classes match these filters" description="Clear a filter, import a section routine, or add a recurring class." /></div> : <><div className="table-wrap"><table><thead><tr><th>When</th><th>Class</th><th>Sections</th><th>Lecturer</th><th>Room</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{routinePage.items.map((row) => <tr key={row.id}><td className="whitespace-nowrap"><p className="font-medium text-slate-100">{days[row.day_of_week]}</p><p className="text-sm text-slate-400">{label("time-slots", row.time_slot_id)}</p></td><td><p className="font-medium text-slate-100">{label("modules", row.module_id)}</p><div className="mt-1"><Badge>{label("class-types", row.class_type_id)}</Badge></div></td><td>{row.section_names?.join(" + ") || label("sections", row.section_id)}</td><td>{label("teachers", row.teacher_id)}</td><td>{label("rooms", row.room_id)}</td><td className="text-right"><Link className="interactive-link" href={`/admin/overrides?routine_id=${row.id}`}>Override</Link></td></tr>)}</tbody></table></div><HorizontalPagination page={routinePage.page} total={routinePage.total} pageSize={pageSize} disabled={masterLoading || tableLoading} onPageChange={setPage} /></>}
    </section>}
  </div>;
}
