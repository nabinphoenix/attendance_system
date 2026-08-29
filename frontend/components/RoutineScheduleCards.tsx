"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/Badge";

type RoutineRow = {
  id: number;
  day_of_week: number;
  module_id: number;
  room_id: number;
  class_type_id: number;
};

type Detail = { label: string; value: string };

const colorTones = [
  { card: "border-l-teal-500 bg-teal-500/[0.045] hover:border-teal-400", time: "border-teal-500/20 bg-teal-500/10 text-teal-700 dark:text-teal-200", marker: "bg-teal-500", label: "bg-teal-500/10 text-teal-700 dark:text-teal-200" },
  { card: "border-l-amber-500 bg-amber-500/[0.045] hover:border-amber-400", time: "border-amber-500/20 bg-amber-500/10 text-amber-800 dark:text-amber-200", marker: "bg-amber-500", label: "bg-amber-500/10 text-amber-800 dark:text-amber-200" },
  { card: "border-l-violet-500 bg-violet-500/[0.045] hover:border-violet-400", time: "border-violet-500/20 bg-violet-500/10 text-violet-800 dark:text-violet-200", marker: "bg-violet-500", label: "bg-violet-500/10 text-violet-800 dark:text-violet-200" },
  { card: "border-l-sky-500 bg-sky-500/[0.045] hover:border-sky-400", time: "border-sky-500/20 bg-sky-500/10 text-sky-800 dark:text-sky-200", marker: "bg-sky-500", label: "bg-sky-500/10 text-sky-800 dark:text-sky-200" },
  { card: "border-l-rose-500 bg-rose-500/[0.045] hover:border-rose-400", time: "border-rose-500/20 bg-rose-500/10 text-rose-800 dark:text-rose-200", marker: "bg-rose-500", label: "bg-rose-500/10 text-rose-800 dark:text-rose-200" },
  { card: "border-l-lime-500 bg-lime-500/[0.045] hover:border-lime-400", time: "border-lime-500/20 bg-lime-500/10 text-lime-800 dark:text-lime-200", marker: "bg-lime-500", label: "bg-lime-500/10 text-lime-800 dark:text-lime-200" },
] as const;

type Props<Row extends RoutineRow> = {
  rows: Row[];
  colorRows?: Row[];
  days: string[];
  colorBy: "module_id" | "room_id";
  colorMeaning: "Subject" | "Classroom";
  time: (row: Row) => string;
  title: (row: Row) => string;
  classType: (row: Row) => string;
  details: (row: Row) => Detail[];
};

export function RoutineScheduleCards<Row extends RoutineRow>({ rows, colorRows = rows, days, colorBy, colorMeaning, time, title, classType, details }: Props<Row>) {
  const tones = useMemo(() => {
    const keys = [...new Set(colorRows.map((row) => String(row[colorBy])))].sort((first, second) => first.localeCompare(second, undefined, { numeric: true }));
    return new Map(keys.map((key, index) => [key, colorTones[index % colorTones.length]]));
  }, [colorBy, colorRows]);

  const groupedRows = useMemo(() => days.map((day, index) => ({
    day,
    index,
    rows: rows.filter((row) => row.day_of_week === index).sort((first, second) => time(first).localeCompare(time(second))),
  })).filter((group) => group.rows.length), [days, rows, time]);

  return <div className="space-y-8">
    <div className="flex flex-wrap items-center gap-2 text-sm app-caption"><span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" /><span>Each {colorMeaning.toLowerCase()} keeps the same color across the week.</span></div>
    {groupedRows.map((group) => <section key={group.day} aria-labelledby={`routine-day-${group.index}`}>
      <div className="mb-3 flex items-center gap-3"><span className="grid h-7 w-7 place-items-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-xs font-bold text-emerald-700 dark:text-emerald-300">{group.day.slice(0, 3)}</span><h2 id={`routine-day-${group.index}`} className="text-lg font-semibold">{group.day}</h2><span className="text-sm app-caption">{group.rows.length} class{group.rows.length === 1 ? "" : "es"}</span></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{group.rows.map((row) => {
        const tone = tones.get(String(row[colorBy])) ?? colorTones[0];
        const [startTime, endTime] = time(row).split("–");
        return <article key={row.id} className={`group relative min-h-48 overflow-hidden rounded-2xl border border-slate-200 border-l-4 p-4 shadow-sm transition duration-200 hover:-translate-y-1 hover:shadow-lg dark:border-slate-800 ${tone.card}`}>
          <div className="flex gap-4"><div className={`flex w-20 shrink-0 flex-col justify-center rounded-xl border px-3 py-3 ${tone.time}`}><span className="text-xl font-bold tracking-tight">{startTime}</span><span className="mt-1 text-xs font-medium opacity-75">– {endTime || ""}</span></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${tone.label}`}><span className={`h-1.5 w-1.5 rounded-full ${tone.marker}`} />{colorMeaning} color</span><Badge>{classType(row)}</Badge></div><h3 className="mt-3 text-base font-semibold leading-5 text-slate-900 dark:text-slate-50">{title(row)}</h3></div></div>
          <dl className="mt-4 grid gap-2 border-t border-slate-200/80 pt-3 text-sm dark:border-slate-700/80">{details(row).map((detail) => <div key={detail.label} className="flex gap-2"><dt className="w-16 shrink-0 text-xs font-medium uppercase tracking-wide app-caption">{detail.label}</dt><dd className="min-w-0 font-medium text-slate-700 dark:text-slate-200">{detail.value}</dd></div>)}</dl>
        </article>;
      })}</div>
    </section>)}
  </div>;
}
