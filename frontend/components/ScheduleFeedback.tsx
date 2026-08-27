import { Badge } from "@/components/ui/Badge";

export type ScheduleConflict = {
  resource: string;
  title: string;
  description: string;
  routine_id: number;
  class_label: string;
  teacher_name: string;
  room_name: string;
  section_names: string[];
  time_range: string;
};

export type AvailabilityState =
  | { status: "incomplete"; message?: string }
  | { status: "checking"; message?: string }
  | { status: "available"; message?: string }
  | { status: "conflict"; conflicts: ScheduleConflict[]; message?: string }
  | { status: "error"; message: string };

export function apiMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (typeof detail?.message === "string") return detail.message;
  return fallback;
}

export function ScheduleFeedback({ state, className = "" }: { state: AvailabilityState; className?: string }) {
  const base = `rounded-xl border p-4 ${className}`;
  if (state.status === "incomplete") return <section aria-live="polite" className={`${base} border-slate-700 bg-slate-950/45`}><div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full border border-slate-600 text-xs text-slate-400">i</span><p className="text-sm text-slate-400">{state.message || "Select the class, lecturer, time, and room to check availability."}</p></div></section>;
  if (state.status === "checking") return <section aria-live="polite" className={`${base} border-blue-500/25 bg-blue-500/5`}><div className="flex items-center gap-3"><span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-blue-300 border-r-transparent"/><p className="text-sm text-blue-200">{state.message || "Checking lecturer, room, and section availability…"}</p></div></section>;
  if (state.status === "available") return <section aria-live="polite" className={`${base} border-emerald-500/25 bg-emerald-500/10`}><div className="flex items-center gap-3"><span aria-hidden="true" className="grid h-6 w-6 place-items-center rounded-full bg-emerald-400 font-bold text-slate-950">✓</span><div><p className="font-semibold text-emerald-200">Time available</p><p className="mt-0.5 text-sm text-emerald-100/80">{state.message || "The selected lecturer, room, and sections are free for this class."}</p></div></div></section>;
  if (state.status === "conflict") return <section role="alert" aria-live="assertive" className={`${base} border-red-500/35 bg-red-500/10`}><div className="flex items-start gap-3"><span aria-hidden="true" className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-red-400 font-bold text-slate-950">!</span><div><p className="font-semibold text-red-100">This time is unavailable</p><p className="mt-0.5 text-sm text-red-200/90">{state.message || "Another scheduled class uses one or more of these resources."}</p></div></div><div className="mt-4 space-y-2">{state.conflicts.map((conflict, index) => <article key={`${conflict.resource}-${conflict.routine_id}-${index}`} className="rounded-lg border border-red-400/20 bg-slate-950/45 p-3"><div className="flex flex-wrap items-center gap-2"><Badge tone="danger">{conflict.title}</Badge><p className="text-sm font-medium text-slate-100">Existing class: {conflict.class_label}</p></div><p className="mt-2 text-sm leading-6 text-slate-300">{conflict.description}</p></article>)}</div></section>;
  return <section role="alert" className={`${base} border-amber-500/30 bg-amber-500/10`}><p className="font-semibold text-amber-100">Availability could not be checked</p><p className="mt-1 text-sm text-amber-200/90">{state.message}</p></section>;
}
