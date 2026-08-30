import { Badge } from "@/components/ui/Badge";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

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
  if (state.status === "incomplete") return <SystemFeedback className={className} title="Ready to check availability" description={state.message || "Select the class, lecturer, time, and room to check availability."} />;
  if (state.status === "checking") return <SystemFeedback className={className} tone="info" title="Checking availability" description={state.message || "Checking lecturer, room, and section availability…"} />;
  if (state.status === "available") return <SystemFeedback className={className} tone="success" title="Time available" description={state.message || "The selected lecturer, room, and sections are free for this class."} />;
  if (state.status === "conflict") return <SystemFeedback className={className} tone="danger" title="This time is unavailable" description={state.message || "Another scheduled class uses one or more of these resources."}>
    <div className="mt-4 space-y-2">{state.conflicts.map((conflict, index) => <article key={`${conflict.resource}-${conflict.routine_id}-${index}`} className="rounded-lg border border-red-400/20 bg-slate-950/45 p-3"><div className="flex flex-wrap items-center gap-2"><Badge tone="danger">{conflict.title}</Badge><p className="text-sm font-medium text-slate-100">Existing class: {conflict.class_label}</p></div><p className="mt-2 text-sm leading-6 text-slate-300">{conflict.description}</p></article>)}</div>
  </SystemFeedback>;
  return <SystemFeedback className={className} tone="warning" title="Availability could not be checked" description={state.message} />;
}
