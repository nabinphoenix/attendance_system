"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

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
    <PageHeader title="My routine" description="Your weekly class schedule, lecturers, and rooms." />
    {loading ? <LoadingState label="Loading your routine…" /> : error ? <ErrorState title="Unable to load routine" description={error} onRetry={load} /> : !rows.length ? <EmptyState title="No routine assigned yet" description="Your classes will appear here once your section timetable is published." /> : <>
      <div className="hidden table-wrap md:block">
        <table>
          <thead><tr><th>Day</th><th>Time</th><th>Module</th><th>Type</th><th>Lecturer</th><th>Room</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.id}>
            <td className="font-medium text-slate-100">{days[row.day_of_week]}</td>
            <td className="whitespace-nowrap font-semibold text-slate-100">{text("time-slots", row.time_slot_id)}</td>
            <td>{text("modules", row.module_id)}</td>
            <td><Badge>{text("class-types", row.class_type_id)}</Badge></td>
            <td>{text("teachers", row.teacher_id)}</td>
            <td>{text("rooms", row.room_id)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="grid gap-3 md:hidden">{rows.map((row) => <article key={row.id} className="panel p-4">
        <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{days[row.day_of_week]}</p><p className="mt-1 text-lg font-semibold text-slate-50">{text("time-slots", row.time_slot_id)}</p></div><Badge>{text("class-types", row.class_type_id)}</Badge></div>
        <h2 className="mt-4 font-semibold text-slate-100">{text("modules", row.module_id)}</h2>
        <dl className="mt-3 grid gap-2 text-sm text-slate-400"><div><dt className="sr-only">Lecturer</dt><dd>{text("teachers", row.teacher_id)}</dd></div><div><dt className="sr-only">Room</dt><dd>{text("rooms", row.room_id)}</dd></div></dl>
      </article>)}</div>
    </>}
  </div>;
}
