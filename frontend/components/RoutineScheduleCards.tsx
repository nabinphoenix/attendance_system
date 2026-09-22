"use client";

import { useMemo } from "react";
import { ModuleScheduleCard, type ScheduleDetail } from "@/components/ModuleScheduleCard";

type RoutineRow = {
  id: number;
  day_of_week: number;
  module_id: number;
  room_id: number;
  class_type_id: number;
};

type Props<Row extends RoutineRow> = {
  rows: Row[];
  colorRows?: Row[];
  days: string[];
  colorBy: "module_id" | "room_id";
  colorMeaning: "Subject" | "Classroom";
  time: (row: Row) => string;
  code?: (row: Row) => string;
  title: (row: Row) => string;
  classType: (row: Row) => string;
  details: (row: Row) => ScheduleDetail[];
};

function splitTime(value: string) {
  const [start = value, end = ""] = value.split(/\s*(?:–|—|â€“|â€”|Ã¢â‚¬â€œ|�|-)\s*/);
  return { start, end };
}

export function RoutineScheduleCards<Row extends RoutineRow>({ rows, colorRows = rows, days, colorBy, colorMeaning, time, code, title, classType, details }: Props<Row>) {
  const accentByKey = useMemo(() => {
    const keys = [...new Set(colorRows.map((row) => String(row[colorBy])))].sort((first, second) => first.localeCompare(second, undefined, { numeric: true }));
    return new Map(keys.map((key, index) => [key, index]));
  }, [colorBy, colorRows]);

  const groupedRows = useMemo(() => days.map((day, index) => ({
    day,
    index,
    rows: rows.filter((row) => row.day_of_week === index).sort((first, second) => time(first).localeCompare(time(second))),
  })).filter((group) => group.rows.length), [days, rows, time]);

  return <div className="space-y-8">
    <div className="flex flex-wrap items-center gap-2 text-sm app-caption"><span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" /><span>Same {colorMeaning.toLowerCase()} colors are used across the week.</span></div>
    {groupedRows.map((group) => <section key={group.day} aria-labelledby={`routine-day-${group.index}`}>
      <div className="mb-4 flex items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-xs font-bold text-emerald-700 dark:text-emerald-300">{group.day.slice(0, 3)}</span><h2 id={`routine-day-${group.index}`} className="text-lg font-bold">{group.day} Schedule</h2></div><span className="text-sm app-caption">{group.rows.length} class{group.rows.length === 1 ? "" : "es"} scheduled</span></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{group.rows.map((row) => {
        const times = splitTime(time(row));
        return <ModuleScheduleCard key={row.id} accentIndex={accentByKey.get(String(row[colorBy])) ?? 0} code={code?.(row)} title={title(row)} startTime={times.start} endTime={times.end} classType={classType(row)} details={details(row)} />;
      })}</div>
    </section>)}
  </div>;
}
