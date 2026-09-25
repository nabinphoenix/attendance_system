"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrorMessage";
import { notifySystemFeedback } from "@/lib/systemFeedback";
import { downloadFile } from "@/lib/download";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const allowedFile = /\.(csv|xlsx)$/i;

type PreviewRow = { row: number; status: string; message: string };
type PreviewError = { row_number: number; error_message: string };
type TimetablePreview = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  new_rows: number;
  existing_rows: number;
  merge_rows: number;
  pending_section_references: number;
  rows: PreviewRow[];
  errors: PreviewError[];
};
type ImportResult = { success_count: number; failed_count: number; file_name: string };

export default function TeacherTimetablePanel() {
  const [teachers, setTeachers] = useState<any[]>([]);
  const [teacherId, setTeacherId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [data, setData] = useState<Record<string, any[]>>({});
  const [preview, setPreview] = useState<TimetablePreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState<"preview" | "import" | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async (id = "") => {
    setLoading(true);
    try {
      const names = ["teachers", "modules", "class-types", "rooms", "blocks", "time-slots", "intakes"];
      const responses = await Promise.all(names.map((name) => api.get("/api/v1/academic/" + name)));
      setTeachers(responses[0].data);
      setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data])));
      if (id) {
        setRows((await api.get("/api/v1/academic/teachers/" + id + "/routines")).data);
      } else {
        setRows([]);
      }
      setError("");
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to load timetable setup."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const find = (kind: string, id: number) => data[kind]?.find((item) => item.id === id);
  const name = (kind: string, id: number) => {
    const item = find(kind, id);
    if (!item) return String(id);
    if (kind === "modules") return item.code + " — " + item.title;
    if (kind === "rooms") return (find("blocks", item.block_id)?.name || "") + " / " + item.name;
    if (kind === "time-slots") return item.start_time.slice(0, 5) + "–" + item.end_time.slice(0, 5);
    return item.name || item.code;
  };
  const supportedFile = Boolean(file && allowedFile.test(file.name));
  const canPreview = Boolean(teacherId && supportedFile && file && !working);
  const canImport = Boolean(canPreview && preview && preview.invalid_rows === 0 && !result);

  function selectFile(selected: File | null) {
    setFile(selected);
    setPreview(null);
    setResult(null);
    setMessage("");
    setError("");
  }

  function selectTeacher(id: string) {
    setTeacherId(id);
    selectFile(null);
    if (input.current) input.current.value = "";
    void load(id);
  }

  async function runPreview(event: FormEvent) {
    event.preventDefault();
    if (!canPreview || !file) return;
    setWorking("preview");
    setError("");
    setMessage("");
    setPreview(null);
    setResult(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const nextPreview = (await api.post<TimetablePreview>("/api/v1/academic/teachers/" + teacherId + "/timetable/preview", body)).data;
      setPreview(nextPreview);
      if (nextPreview.invalid_rows > 0) {
        notifySystemFeedback({
          tone: "warning",
          title: "Routine preview found " + String(nextPreview.invalid_rows) + " invalid row(s)",
          description: "Review the row numbers and reasons below, correct the file, then preview it again.",
        });
      } else {
        notifySystemFeedback({
          tone: "success",
          title: "Routine preview is ready",
          description: String(nextPreview.valid_rows) + " row(s) passed validation. Review the changes before importing.",
        });
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "The timetable file could not be previewed."));
    } finally {
      setWorking(null);
    }
  }

  async function submit() {
    if (!canImport || !file) return;
    setWorking("import");
    setError("");
    setMessage("");
    const body = new FormData();
    body.append("file", file);
    try {
      const imported = (await api.post<ImportResult>("/api/v1/academic/teachers/" + teacherId + "/timetable/import", body)).data;
      setResult(imported);
      setMessage("Imported " + String(imported.success_count) + " row(s); " + String(imported.failed_count) + " failed.");
      setFile(null);
      if (input.current) input.current.value = "";
      await load(teacherId);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "The timetable could not be imported."));
    } finally {
      setWorking(null);
    }
  }

  const template = "/api/v1/academic/teachers/" + teacherId + "/timetable/template?format=";
  const exportUrl = "/api/v1/academic/teachers/" + teacherId + "/timetable/export?format=";

  return <section className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-5">
    <h2 className="text-2xl font-bold">Teacher profile and timetable</h2>
    <p className="mt-1 text-sm text-slate-400">Select a teacher to review their timetable or preview a file before importing it.</p>

    {error && <SystemFeedback className="mt-4" tone="danger" title="Timetable action needs attention" description={error} />}
    {message && <SystemFeedback className="mt-4" tone="success" title="Import result" description={message} />}

    <div className="mt-4 flex flex-wrap gap-3">
      <label className="sr-only" htmlFor="teacher-timetable-teacher">Select teacher</label>
      <select id="teacher-timetable-teacher" value={teacherId} disabled={loading || working !== null} onChange={(event) => selectTeacher(event.target.value)}>
        <option value="">Select teacher</option>
        {teachers.map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.name} ({teacher.employee_code})</option>)}
      </select>
      {teacherId && <>
        <Button type="button" variant="outline" disabled={loading} onClick={() => void downloadFile(template + "csv", "teacher_timetable_template.csv")}>CSV template</Button>
        <Button type="button" variant="outline" disabled={loading} onClick={() => void downloadFile(template + "xlsx", "teacher_timetable_template.xlsx")}>XLSX template</Button>
        <Button type="button" variant="outline" disabled={loading} onClick={() => void downloadFile(exportUrl + "csv", "teacher_timetable.csv")}>Export CSV</Button>
        <Button type="button" variant="outline" disabled={loading} onClick={() => void downloadFile(exportUrl + "xlsx", "teacher_timetable.xlsx")}>Export XLSX</Button>
      </>}
    </div>

    <form onSubmit={runPreview} className="mt-4 flex flex-wrap items-start gap-3">
      <label className="block text-sm"><span className="sr-only">Routine CSV or Excel file</span><input ref={input} type="file" accept=".csv,.xlsx" disabled={working !== null} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} /></label>
      <Button type="submit" variant="outline" loading={working === "preview"} disabled={!canPreview}>{working === "preview" ? "Validating..." : "Preview validation"}</Button>
      <Button type="button" loading={working === "import"} disabled={!canImport} onClick={() => void submit()}>{working === "import" ? "Importing..." : "Import timetable"}</Button>
    </form>
    {file && !supportedFile && <p role="alert" className="mt-2 text-sm text-red-300">This file type is not supported. Choose a .csv or .xlsx file.</p>}
    {teacherId && file && !preview && <p role="status" className="mt-2 text-sm text-amber-300">Preview this file before importing so the system can identify missing or incorrect rows.</p>}
    {preview?.invalid_rows ? <p role="status" className="mt-2 text-sm text-amber-300">Fix all invalid rows in the preview before importing.</p> : null}
    {preview && !preview.invalid_rows && !result && <p role="status" className="mt-2 text-sm text-slate-400">Check the preview summary and row outcomes. Import becomes available when validation passes.</p>}

    {preview && <section className="mt-4 rounded-xl border border-slate-700 p-4" aria-labelledby="teacher-timetable-preview">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="teacher-timetable-preview" className="font-semibold">Validation preview</h3>
        <Badge tone={preview.invalid_rows ? "warning" : "success"}>{preview.invalid_rows ? "Needs attention" : "Ready to import"}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-6">
        {[
          ["Rows", preview.total_rows],
          ["Valid", preview.valid_rows],
          ["New", preview.new_rows],
          ["Existing", preview.existing_rows],
          ["Merge", preview.merge_rows],
          ["Invalid", preview.invalid_rows],
        ].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-slate-950/60 p-3">
          <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
          <p className={"mt-1 text-xl font-semibold " + (label === "Invalid" && value ? "text-red-300" : "text-slate-100")}>{value}</p>
        </div>)}
      </div>
      <div className="mt-4 max-h-72 overflow-auto table-wrap" role="region" aria-label="Teacher timetable row validation results" tabIndex={0}>
        <table><thead><tr><th>Row</th><th>Status</th><th>System feedback</th></tr></thead><tbody>
          {preview.rows.map((row) => <tr key={"valid-" + String(row.row)}><td>{row.row}</td><td><Badge tone="success">{row.status.replace("valid_", "").toUpperCase()}</Badge></td><td>{row.message}</td></tr>)}
          {preview.errors.map((row) => <tr key={"error-" + String(row.row_number)}><td>{row.row_number}</td><td><Badge tone="danger">Invalid</Badge></td><td className="text-red-300">{row.error_message}</td></tr>)}
        </tbody></table>
      </div>
    </section>}

    <div className="mt-5 overflow-x-auto" role="region" aria-label="Teacher timetable" tabIndex={0}>
      <table className="w-full text-left text-sm">
        <thead><tr><th>Day / time</th><th>Intake</th><th>Sections</th><th>Course</th><th>Type</th><th>Room</th></tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.id} className="border-t border-slate-800">
            <td className="py-2">{days[row.day_of_week]}<br />{name("time-slots", row.time_slot_id)}</td>
            <td>{name("intakes", row.intake_id)}</td>
            <td>{row.section_names?.join(" + ")}</td>
            <td>{name("modules", row.module_id)}</td>
            <td>{name("class-types", row.class_type_id)}</td>
            <td>{name("rooms", row.room_id)}</td>
          </tr>)}
          {!loading && teacherId && !rows.length && <tr><td className="py-4 text-slate-400" colSpan={6}>No routine entries for this teacher.</td></tr>}
          {loading && <tr><td className="py-4 text-slate-400" colSpan={6}>Loading teacher timetable...</td></tr>}
        </tbody>
      </table>
    </div>
  </section>;
}