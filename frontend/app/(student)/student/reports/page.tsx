"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { downloadFile } from "@/lib/download";

type SubjectAttendance = {
  subject_id: number;
  subject_name: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
};

type AttendanceSummary = {
  overall_percentage: number;
  present: number;
  absent: number;
  total: number;
  subjects: SubjectAttendance[];
  attendance_threshold_percent: number;
  minimum_observations: number;
};

function percentage(value: number) {
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

export default function Page() {
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get<AttendanceSummary>("/api/v1/analytics/my-attendance-summary");
      setSummary(response.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load your attendance report.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const subjects = useMemo(
    () => summary?.subjects.toSorted((left, right) => left.percentage - right.percentage) ?? [],
    [summary],
  );

  if (loading) return <LoadingState label="Loading attendance report" />;
  if (error) return <ErrorState title="Unable to load your attendance" description={error} onRetry={() => void load()} />;
  if (!summary) return null;

  const threshold = summary.attendance_threshold_percent;
  const observations = summary.minimum_observations;
  const belowThreshold = subjects.filter((subject) => subject.total >= observations && subject.percentage < threshold).length;
  const overallTone = summary.overall_percentage < threshold ? "danger" : "success";

  const status = (subject: SubjectAttendance) => {
    if (subject.total < observations) return <Badge tone="neutral">Building baseline</Badge>;
    return subject.percentage < threshold ? <Badge tone="danger">Below threshold</Badge> : <Badge tone="success">On track</Badge>;
  };

  const row = (subject: SubjectAttendance) => <tr key={subject.subject_id}>
    <td className="font-medium text-slate-100">{subject.subject_name}</td>
    <td>{subject.present}</td>
    <td>{subject.absent}</td>
    <td>{subject.total}</td>
    <td className="min-w-44"><div className="flex items-center gap-3"><div className="h-2 min-w-20 flex-1 overflow-hidden rounded-full bg-slate-800"><div className={subject.percentage < threshold && subject.total >= observations ? "h-full bg-red-400" : "h-full bg-emerald-400"} style={{ width: `${Math.max(0, Math.min(subject.percentage, 100))}%` }} /></div><span className="w-12 text-right font-semibold">{percentage(subject.percentage)}</span></div></td>
    <td>{status(subject)}</td>
  </tr>;

  return <div className="max-w-6xl">
    <PageHeader title="My attendance report" description="Your attendance is calculated from completed classes only." action={<div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void downloadFile("/api/v1/analytics/my-attendance-summary.csv", "my_attendance_analysis.csv")}>Export analysis CSV</Button><Button variant="outline" onClick={() => void load()}>Refresh</Button></div>} />

    <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div className="panel p-5"><p className="text-sm text-slate-400">Overall attendance</p><p className="mt-2 text-3xl font-semibold text-slate-50">{percentage(summary.overall_percentage)}</p><p className="mt-3 text-sm text-slate-400">{summary.present} present · {summary.absent} absent · {summary.total} completed classes</p><div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800"><div className={overallTone === "danger" ? "h-full bg-red-400" : "h-full bg-emerald-400"} style={{ width: `${Math.max(0, Math.min(summary.overall_percentage, 100))}%` }} /></div></div>
      <div className="panel p-5"><p className="text-sm text-slate-400">Required threshold</p><p className="mt-2 text-3xl font-semibold text-slate-50">{percentage(threshold)}</p><p className="mt-4 text-sm text-slate-400">Measured after {observations} completed classes in a subject.</p></div>
      <div className="panel p-5"><p className="text-sm text-slate-400">Subjects below threshold</p><p className={`mt-2 text-3xl font-semibold ${belowThreshold ? "text-red-300" : "text-emerald-300"}`}>{belowThreshold}</p><p className="mt-4 text-sm text-slate-400">Focus on these subjects to protect your overall attendance.</p></div>
    </section>

    <section className="mt-8"><div className="mb-3"><h2 className="text-xl font-semibold">Subject-wise attendance</h2><p className="mt-1 text-sm text-slate-400">You are below the threshold when your attendance is under {percentage(threshold)} after {observations} or more completed classes.</p></div>
      {!subjects.length ? <div className="panel"><EmptyState title="No completed classes yet" description="Your subject attendance will appear here after classes are completed." /></div> : <div className="table-wrap"><table><thead><tr><th>Subject</th><th>Present</th><th>Absent</th><th>Total</th><th>Attendance</th><th>Status</th></tr></thead><tbody>{subjects.map(row)}</tbody></table></div>}
    </section>
  </div>;
}
