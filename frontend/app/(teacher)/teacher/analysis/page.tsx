"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type AnalysisScope = {
  module_id: number;
  module_name: string;
  module_code: string | null;
  section_id: number;
  section_name: string;
};

type ClassTypeStat = {
  class_type_id: number | null;
  class_type_name: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
};

type StudentStat = {
  student_id: number;
  student_name: string;
  roll_number: string;
  present: number;
  absent: number;
  total: number;
  percentage: number;
  attendance_status: "regular" | "needs_attention" | "building_baseline";
};

type TeacherAnalysis = {
  teacher_id: number;
  date_from: string | null;
  date_to: string | null;
  present: number;
  absent: number;
  total: number;
  overall_percentage: number;
  scopes: AnalysisScope[];
  available_class_types: ClassTypeStat[];
  students: StudentStat[];
  class_types: ClassTypeStat[];
  attendance_threshold_percent: number;
  minimum_observations: number;
};

type Filters = {
  module: string;
  section: string;
  classType: string;
  dateFrom: string;
  dateTo: string;
  student: string;
  attendanceStatus: string;
};

const emptyFilters: Filters = { module: "", section: "", classType: "", dateFrom: "", dateTo: "", student: "", attendanceStatus: "" };

function percentage(value: number) {
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function statusBadge(status: StudentStat["attendance_status"]) {
  if (status === "regular") return <Badge tone="success">Regular</Badge>;
  if (status === "needs_attention") return <Badge tone="danger">Needs attention</Badge>;
  return <Badge tone="neutral">Building baseline</Badge>;
}

export default function Page() {
  const [analysis, setAnalysis] = useState<TeacherAnalysis | null>(null);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (nextFilters: Filters) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (nextFilters.module) params.set("module_id", nextFilters.module);
      if (nextFilters.section) params.set("section_id", nextFilters.section);
      if (nextFilters.classType) params.set("class_type_id", nextFilters.classType);
      if (nextFilters.dateFrom) params.set("date_from", nextFilters.dateFrom);
      if (nextFilters.dateTo) params.set("date_to", nextFilters.dateTo);
      const query = params.toString();
      const response = await api.get<TeacherAnalysis>(`/api/v1/analytics/teacher-attendance-analysis${query ? `?${query}` : ""}`);
      setAnalysis(response.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load your class attendance analysis.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(emptyFilters); }, [load]);

  const modules = useMemo(() => {
    const byId = new Map<number, Pick<AnalysisScope, "module_id" | "module_name" | "module_code">>();
    analysis?.scopes.forEach((scope) => byId.set(scope.module_id, scope));
    return [...byId.values()].toSorted((left, right) => left.module_name.localeCompare(right.module_name));
  }, [analysis]);

  const sections = useMemo(() => {
    const byId = new Map<number, AnalysisScope>();
    (analysis?.scopes ?? []).filter((scope) => !filters.module || String(scope.module_id) === filters.module).forEach((scope) => {
      if (!byId.has(scope.section_id)) byId.set(scope.section_id, scope);
    });
    return [...byId.values()].toSorted((left, right) => left.section_name.localeCompare(right.section_name));
  }, [analysis, filters.module]);

  const students = useMemo(() => (analysis?.students ?? []).filter((student) => {
    if (filters.attendanceStatus && student.attendance_status !== filters.attendanceStatus) return false;
    if (filters.student) {
      const query = filters.student.toLowerCase();
      return `${student.student_name} ${student.roll_number}`.toLowerCase().includes(query);
    }
    return true;
  }), [analysis, filters.attendanceStatus, filters.student]);

  const topRegular = useMemo(() => (analysis?.students ?? []).filter((student) => student.attendance_status === "regular").toSorted((left, right) => right.percentage - left.percentage)[0], [analysis]);
  const mostAtRisk = analysis?.students[0];
  const mostMissedClassType = useMemo(() => analysis?.class_types.toSorted((left, right) => left.percentage - right.percentage)[0], [analysis]);

  function changeFilter(key: keyof Filters, value: string) {
    setFilters((current) => {
      const next = { ...current, [key]: value };
      if (key === "module" && current.section && !analysis?.scopes.some((scope) => String(scope.module_id) === value && String(scope.section_id) === current.section)) next.section = "";
      return next;
    });
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo) {
      setError("Choose a valid date range. The start date must be on or before the end date.");
      return;
    }
    void load(filters);
  }

  function clearFilters() {
    setFilters(emptyFilters);
    void load(emptyFilters);
  }

  if (loading && !analysis) return <LoadingState label="Loading attendance analysis" />;
  if (error && !analysis) return <ErrorState title="Unable to load attendance analysis" description={error} onRetry={() => void load(filters)} />;
  if (!analysis) return null;

  return <div className="max-w-screen-2xl">
    <PageHeader title="Attendance analysis" description="Review attendance only for your assigned modules and sections. Completed classes are included." action={<Button type="button" variant="outline" onClick={() => void load(filters)}>Refresh</Button>} />

    <form onSubmit={applyFilters} className="panel mt-6 p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Report filters</h2><p className="mt-1 text-sm text-slate-400">Narrow results by the module, section, class type, or completed-class date.</p></div><Button type="button" variant="ghost" onClick={clearFilters}>Clear filters</Button></div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <label><span className="field-label">Module</span><select value={filters.module} onChange={(event) => changeFilter("module", event.target.value)}><option value="">All assigned modules</option>{modules.map((module) => <option key={module.module_id} value={module.module_id}>{module.module_code ? `${module.module_code} - ` : ""}{module.module_name}</option>)}</select></label>
        <label><span className="field-label">Section</span><select value={filters.section} onChange={(event) => changeFilter("section", event.target.value)}><option value="">All assigned sections</option>{sections.map((section) => <option key={section.section_id} value={section.section_id}>{section.section_name}</option>)}</select></label>
        <label><span className="field-label">Class type</span><select value={filters.classType} onChange={(event) => changeFilter("classType", event.target.value)}><option value="">All class types</option>{analysis.available_class_types.map((item) => <option key={item.class_type_id} value={item.class_type_id ?? ""}>{item.class_type_name}</option>)}</select></label>
        <label><span className="field-label">From date</span><input type="date" value={filters.dateFrom} onChange={(event) => changeFilter("dateFrom", event.target.value)} /></label>
        <label><span className="field-label">To date</span><input type="date" value={filters.dateTo} onChange={(event) => changeFilter("dateTo", event.target.value)} /></label>
      </div>
      <div className="mt-3 flex justify-end"><Button type="submit" loading={loading}>Apply report filters</Button></div>
    </form>

    {error && <div className="mt-5"><ErrorState title="Unable to update attendance analysis" description={error} onRetry={() => void load(filters)} /></div>}

    <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <article className="panel p-5"><p className="text-sm text-slate-400">Class attendance</p><p className={`mt-2 text-3xl font-semibold ${analysis.overall_percentage < analysis.attendance_threshold_percent && analysis.total >= analysis.minimum_observations ? "text-red-300" : "text-emerald-300"}`}>{percentage(analysis.overall_percentage)}</p><p className="mt-2 text-sm text-slate-400">{analysis.present} present/late - {analysis.absent} missed</p></article>
      <article className="panel p-5"><p className="text-sm text-slate-400">Students needing attention</p><p className="mt-2 text-3xl font-semibold text-red-300">{analysis.students.filter((student) => student.attendance_status === "needs_attention").length}</p><p className="mt-2 text-sm text-slate-400">Below {percentage(analysis.attendance_threshold_percent)} after {analysis.minimum_observations} classes</p></article>
      <article className="panel p-5"><p className="text-sm text-slate-400">Lowest attendance</p><p className="mt-2 truncate text-xl font-semibold text-slate-100">{mostAtRisk?.student_name ?? "No data yet"}</p><p className="mt-2 text-sm text-slate-400">{mostAtRisk ? `${percentage(mostAtRisk.percentage)} - ${mostAtRisk.absent} missed` : "Complete attendance to see insight"}</p></article>
      <article className="panel p-5"><p className="text-sm text-slate-400">Most missed class type</p><p className="mt-2 truncate text-xl font-semibold text-slate-100">{mostMissedClassType?.class_type_name ?? "No data yet"}</p><p className="mt-2 text-sm text-slate-400">{mostMissedClassType ? `${percentage(mostMissedClassType.percentage)} attendance` : "Complete attendance to see insight"}</p></article>
    </section>

    <section className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,.75fr)]">
      <div className="panel p-5">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">Student attendance</h2><p className="mt-1 text-sm text-slate-400">Find regular students and students who need support in the selected class scope.</p></div><p className="text-sm text-slate-400">{students.length} of {analysis.students.length} students shown</p></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label><span className="field-label">Find a student</span><input placeholder="Name or roll number" value={filters.student} onChange={(event) => changeFilter("student", event.target.value)} /></label>
          <label><span className="field-label">Student attendance</span><select value={filters.attendanceStatus} onChange={(event) => changeFilter("attendanceStatus", event.target.value)}><option value="">All students</option><option value="regular">Regular students</option><option value="needs_attention">Needs attention</option><option value="building_baseline">Building baseline</option></select></label>
        </div>
        {!students.length ? <div className="mt-5"><EmptyState title="No student attendance matches these filters" description="Try another section, class type, date range, or student filter." /></div> : <div className="table-wrap mt-5"><table><thead><tr><th>Student</th><th>Present</th><th>Missed</th><th>Attendance</th><th>Status</th></tr></thead><tbody>{students.map((student) => <tr key={student.student_id}><td><p className="font-medium text-slate-100">{student.student_name}</p><p className="mt-0.5 text-xs text-slate-400">{student.roll_number}</p></td><td>{student.present}</td><td>{student.absent}</td><td className="min-w-40"><div className="flex items-center gap-2"><div className="h-2 min-w-16 flex-1 overflow-hidden rounded-full bg-slate-800"><div className={student.attendance_status === "needs_attention" ? "h-full bg-red-400" : "h-full bg-emerald-400"} style={{ width: `${Math.max(0, Math.min(student.percentage, 100))}%` }} /></div><span className="w-12 text-right font-semibold">{percentage(student.percentage)}</span></div></td><td>{statusBadge(student.attendance_status)}</td></tr>)}</tbody></table></div>}
      </div>

      <aside className="space-y-5">
        <section className="panel p-5"><h2 className="text-lg font-semibold">Class-type pattern</h2><p className="mt-1 text-sm text-slate-400">Which delivery type has the most absences in this report.</p>{!analysis.class_types.length ? <p className="mt-5 text-sm text-slate-400">No completed classes in this scope yet.</p> : <div className="mt-5 space-y-4">{analysis.class_types.map((item) => <div key={item.class_type_id}><div className="flex items-center justify-between gap-3 text-sm"><span className="font-medium">{item.class_type_name}</span><span className="font-semibold">{percentage(item.percentage)}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className={item.percentage < analysis.attendance_threshold_percent ? "h-full bg-red-400" : "h-full bg-emerald-400"} style={{ width: `${Math.max(0, Math.min(item.percentage, 100))}%` }} /></div><p className="mt-1 text-xs text-slate-400">{item.present} present/late - {item.absent} missed - {item.total} completed</p></div>)}</div>}</section>
        <section className="panel p-5"><h2 className="text-lg font-semibold">Positive signal</h2>{topRegular ? <><p className="mt-3 font-semibold text-emerald-300">{topRegular.student_name}</p><p className="mt-1 text-sm text-slate-400">Highest regular attendance in this selection: {percentage(topRegular.percentage)}.</p></> : <p className="mt-3 text-sm text-slate-400">A regular-attendance insight appears after students meet the observation baseline.</p>}</section>
      </aside>
    </section>
  </div>;
}
