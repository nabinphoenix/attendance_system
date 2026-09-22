"use client";

import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { RoutineScheduleCards } from "@/components/RoutineScheduleCards";
import { ScheduleFilterBar } from "@/components/ScheduleFilterBar";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Page() {
  const [rows, setRows] = useState<any[]>([]);
  const [data, setData] = useState<Record<string, any[]>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ day: "", classType: "" });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [routineResponse, catalogResponse] = await Promise.all([
        api.get("/api/v1/academic/routines/me"),
        api.get("/api/v1/academic/catalog"),
      ]);
      setRows(routineResponse.data);
      setData(catalogResponse.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load your routine.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const find = (kind: string, id: number) => data[kind]?.find((item) => item.id === id);
  const text = (kind: string, id: number) => {
    const item = find(kind, id);
    if (!item) return "Not assigned";
    if (kind === "modules") return item.title;
    if (kind === "module-codes") return item.code;
    if (kind === "time-slots") return `${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}`;
    if (kind === "teachers") return item.name;
    if (kind === "rooms") return [find("blocks", item.block_id)?.name, item.name].filter(Boolean).join("-");
    return item.name;
  };

  const filteredRows = useMemo(() => rows.filter((row) => (!filters.day || String(row.day_of_week) === filters.day) && (!filters.classType || String(row.class_type_id) === filters.classType)), [filters, rows]);
  const clearFilters = () => setFilters({ day: "", classType: "" });

  return <div>
    <PageHeader title="My routine" description="Your weekly class schedule, lecturers, and rooms." action={<span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300">{filteredRows.length} classes this week</span>} />
    {loading ? <LoadingState label="Loading your routine…" /> : error ? <ErrorState title="Unable to load routine" description={error} onRetry={load} /> : !rows.length ? <EmptyState title="No routine assigned yet" description="Your classes will appear here once your section timetable is published." /> : <>
      <div className="mb-6"><ScheduleFilterBar days={days} day={filters.day} onDayChange={(day) => setFilters((current) => ({ ...current, day }))} classType={filters.classType} onClassTypeChange={(classType) => setFilters((current) => ({ ...current, classType }))} classTypes={(data["class-types"] || []).map((item) => ({ value: String(item.id), label: item.name }))} onClear={clearFilters} /></div>
      {!filteredRows.length ? <EmptyState title="No classes match these filters" description="Choose another day or class type." /> : <RoutineScheduleCards rows={filteredRows} days={days} colorBy="module_id" colorMeaning="Subject" code={(row) => text("module-codes", row.module_id)} time={(row) => text("time-slots", row.time_slot_id)} title={(row) => text("modules", row.module_id)} classType={(row) => text("class-types", row.class_type_id)} details={(row) => [{ label: "Lecturer", value: text("teachers", row.teacher_id), icon: "person" }, { label: "Room", value: text("rooms", row.room_id), icon: "pin" }]} />}
    </>}
  </div>;
}
