import type { ReactNode } from "react";

export type ScheduleDetail = {
  label: string;
  value: string;
  icon?: "person" | "pin" | "group";
};

type ModuleScheduleCardProps = {
  code?: string;
  title: string;
  startTime: string;
  endTime: string;
  classType?: string;
  details: ScheduleDetail[];
  accentIndex?: number;
  status?: string;
  cancelled?: boolean;
  children?: ReactNode;
};

const accents = [
  { border: "border-l-teal-500", dot: "bg-teal-500", code: "text-teal-600 dark:text-teal-300", time: "border-teal-500/20 bg-teal-500/10 text-teal-700 dark:text-teal-200" },
  { border: "border-l-indigo-500", dot: "bg-indigo-500", code: "text-indigo-600 dark:text-indigo-300", time: "border-indigo-500/20 bg-indigo-500/10 text-indigo-700 dark:text-indigo-200" },
  { border: "border-l-sky-500", dot: "bg-sky-500", code: "text-sky-600 dark:text-sky-300", time: "border-sky-500/20 bg-sky-500/10 text-sky-700 dark:text-sky-200" },
  { border: "border-l-violet-500", dot: "bg-violet-500", code: "text-violet-600 dark:text-violet-300", time: "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-200" },
  { border: "border-l-rose-500", dot: "bg-rose-500", code: "text-rose-600 dark:text-rose-300", time: "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-200" },
  { border: "border-l-amber-500", dot: "bg-amber-500", code: "text-amber-700 dark:text-amber-300", time: "border-amber-500/20 bg-amber-500/10 text-amber-800 dark:text-amber-200" },
] as const;

function DetailIcon({ icon }: { icon: ScheduleDetail["icon"] }) {
  if (icon === "pin") return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg>;
  if (icon === "group") return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20" /><circle cx="10" cy="8" r="3" /><path d="M16 11a3 3 0 1 0 0-6m4 15v-1.5a3.5 3.5 0 0 0-2.5-3.36" /></svg>;
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="7" r="3" /><path d="M5 21a7 7 0 0 1 14 0" /></svg>;
}

export function ModuleScheduleCard({ code, title, startTime, endTime, classType, details, accentIndex = 0, status, cancelled = false, children }: ModuleScheduleCardProps) {
  const accent = accents[Math.abs(accentIndex) % accents.length];
  const label = status || classType;

  return <article className={`relative overflow-hidden rounded-2xl border border-l-4 border-slate-200 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900 ${accent.border} ${cancelled ? "border-red-500/40 bg-red-50/40 dark:bg-red-950/20" : ""}`}>
    <div className="flex items-start justify-between gap-3">
      <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-semibold ${accent.time}`}>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></svg>
        <span>{startTime}</span><span className="font-normal opacity-70">– {endTime}</span>
      </div>
      {label && <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${cancelled ? "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300" : "border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}>{label}</span>}
    </div>

    {code && <p className={`mt-4 flex items-center gap-2 text-xs font-bold tracking-wide ${accent.code}`}><span className={`h-2 w-2 rounded-full ${accent.dot}`} />{code}</p>}
    <h3 className="mt-2 line-clamp-2 text-base font-bold leading-6 text-slate-900 dark:text-slate-50">{title}</h3>

    {details.length > 0 && <dl className="mt-4 space-y-2 border-t border-slate-200 pt-3 text-sm dark:border-slate-700">
      {details.map((detail, index) => <div key={`${detail.label}-${index}`} className="flex min-w-0 items-center gap-2 text-slate-600 dark:text-slate-300">
        <span className="shrink-0 text-slate-500 dark:text-slate-400"><DetailIcon icon={detail.icon || (index === 0 ? "person" : "pin")} /></span>
        <dt className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{detail.label}:</dt>
        <dd className="min-w-0 truncate font-semibold">{detail.value}</dd>
      </div>)}
    </dl>}
    {children}
  </article>;
}
