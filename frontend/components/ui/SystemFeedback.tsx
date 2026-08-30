import type { ReactNode } from "react";

export type FeedbackTone = "neutral" | "info" | "success" | "warning" | "danger";

const tones: Record<FeedbackTone, string> = {
  neutral: "neutral",
  info: "info",
  success: "success",
  warning: "warning",
  danger: "danger",
};

function FeedbackIcon({ tone }: { tone: FeedbackTone }) {
  if (tone === "success") return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" className="h-4 w-4"><path d="m5 12 4.2 4.2L19 6.5" /></svg>;
  if (tone === "danger") return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" className="h-4 w-4"><path d="M12 8v4m0 4h.01M5.2 19h13.6c1.1 0 1.8-1.2 1.3-2.1L13.3 5.1a1.5 1.5 0 0 0-2.6 0L3.9 16.9c-.5.9.2 2.1 1.3 2.1Z" /></svg>;
  if (tone === "warning") return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" className="h-4 w-4"><path d="M12 8v4m0 4h.01M5.2 19h13.6c1.1 0 1.8-1.2 1.3-2.1L13.3 5.1a1.5 1.5 0 0 0-2.6 0L3.9 16.9c-.5.9.2 2.1 1.3 2.1Z" /></svg>;
  if (tone === "info") return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" className="h-4 w-4"><path d="M12 11v5m0-9h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" className="h-4 w-4"><path d="M12 8v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
}

export function SystemFeedback({
  tone = "neutral",
  title,
  description,
  action,
  children,
  className = "",
}: {
  tone?: FeedbackTone;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return <section role={tone === "danger" ? "alert" : "status"} aria-live={tone === "danger" ? "assertive" : "polite"} className={`system-feedback system-feedback-${tones[tone]} rounded-xl border p-4 ${className}`}>
    <div className="flex items-start gap-3">
      <span aria-hidden="true" className="system-feedback-icon grid h-7 w-7 shrink-0 place-items-center rounded-full border"><FeedbackIcon tone={tone} /></span>
      <div className="min-w-0 flex-1">
        <p className="system-feedback-title font-semibold">{title}</p>
        {description && <div className="system-feedback-description mt-1 text-sm leading-6">{description}</div>}
        {children}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  </section>;
}
