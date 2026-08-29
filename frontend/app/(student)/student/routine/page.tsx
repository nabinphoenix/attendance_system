"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { RoutineScheduleCards } from "@/components/RoutineScheduleCards";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Page() {
  const [rows, setRows] = useState<any[]>([]);
  const [data, setData] = useState<Record<string, any[]>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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

  useEffect(() => { load(); }, []);

  const find = (kind: string, id: number) => data[kind]?.find((item) => item.id === id);
  const text = (kind: string, id: number) => {
    const item = find(kind, id);
    if (!item) return "Not assigned";
    if (kind === "modules") return `${item.code} — ${item.title}`;
    if (kind === "time-slots") return `${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}`;
    if (kind === "teachers") return item.name;
    if (kind === "rooms") return [find("blocks", item.block_id)?.name, item.name].filter(Boolean).join("-");
    return item.name;
  };

  return <div>
    <PageHeader title="My routine" description="Your weekly class schedule, lecturers, and rooms." action={<span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300">{rows.length} classes this week</span>} />
    {loading ? <LoadingState label="Loading your routine…" /> : error ? <ErrorState title="Unable to load routine" description={error} onRetry={load} /> : !rows.length ? <EmptyState title="No routine assigned yet" description="Your classes will appear here once your section timetable is published." /> : <>
      <RoutineScheduleCards rows={rows} days={days} colorBy="module_id" colorMeaning="Subject" time={(row) => text("time-slots", row.time_slot_id)} title={(row) => text("modules", row.module_id)} classType={(row) => text("class-types", row.class_type_id)} details={(row) => [{ label: "Lecturer", value: text("teachers", row.teacher_id) }, { label: "Room", value: text("rooms", row.room_id) }]} />
    </>}
  </div>;
}
