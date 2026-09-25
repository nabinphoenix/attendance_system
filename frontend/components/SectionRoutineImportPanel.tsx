"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrorMessage";
import { notifySystemFeedback } from "@/lib/systemFeedback";
import { downloadFile } from "@/lib/download";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

const setupLinks = [
  ["Programs", "/admin/academic/programs"],
  ["Batches", "/admin/academic/batches"],
  ["Levels & Intake Codes", "/admin/academic/intakes"],
  ["Courses", "/admin/academic/modules"],
  ["Course Assignments", "/admin/academic/module-offerings"],
  ["Teachers", "/admin/academic/teachers"],
  ["Rooms and blocks", "/admin/academic/rooms"],
  ["Class types", "/admin/academic/class-types"],
  ["Time slots", "/admin/academic/time-slots"],
];

const text = (item: any) => item?.name || item?.code || "-";

export default function SectionRoutineImportPanel() {
  const [data, setData] = useState<Record<string, any[]>>({});
  const [batchId, setBatchId] = useState("");
  const [levelId, setLevelId] = useState("");
  const [semesterId, setSemesterId] = useState("");
  const [section, setSection] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [pendingSections, setPendingSections] = useState<any[]>([]);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState<"preview" | "import" | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const names = ["programs", "batches", "intakes", "cohort-semesters", "sections", "modules", "module-offerings", "teachers", "blocks", "rooms", "class-types", "time-slots"];
    Promise.all(names.map((name) => api.get(`/api/v1/academic/${name}`)))
      .then((responses) => setData(Object.fromEntries(names.map((name, index) => [name, responses[index].data]))))
      .catch((requestError) => {
        const message = apiErrorMessage(requestError, "Unable to load academic setup.");
        setError(message);
      });
  }, []);


  const selectedBatch = data.batches?.find((item) => item.id === Number(batchId));
  const levels = [...(selectedBatch?.levels || [])].sort((left, right) => left.level_number - right.level_number);
  const selectedLevel = levels.find((item) => item.id === Number(levelId));
  const semesters = (data["cohort-semesters"] || []).filter((item) => item.batch_id === selectedBatch?.id && item.batch_level_id === selectedLevel?.id && item.intake_id === selectedLevel?.intake_id)
    .sort((left, right) => left.semester_number - right.semester_number || left.attempt_number - right.attempt_number);
  const selectedSemester = semesters.find((item) => item.id === Number(semesterId));
  const intake = String(selectedSemester?.intake_id || "");
  const semester = String(selectedSemester?.semester_number || "");

  useEffect(() => {
    if (!intake || !semester || !section) {
      setPendingSections([]);
      return;
    }
    api.get(`/api/v1/academic/sections/${section}/routine/pending?intake_id=${intake}&semester_number=${semester}`)
      .then((response) => setPendingSections(response.data))
      .catch(() => setPendingSections([]));
  }, [intake, semester, section]);
  const selectedIntake = data.intakes?.find((item) => item.id === Number(intake));
  const selectedSection = data.sections?.find((item) => item.id === Number(section));
  const selectedProgram = data.programs?.find((item) => item.id === selectedBatch?.program_id);
  const eligibleSections = (data.sections || []).filter((item) => item.batch_id === selectedBatch?.id);
  const contextOfferings = (data["module-offerings"] || []).filter((item) =>
    item.is_active &&
    item.intake_id === Number(intake) &&
    item.batch_id === selectedSection?.batch_id &&
    item.semester_number === Number(semester) &&
    item.section_ids?.includes(Number(section)),
  );
  const supportedFile = Boolean(file && /\.(csv|xlsx)$/i.test(file.name));
  const contextSelected = Boolean(batchId && levelId && semesterId && section);
  const sectionConfigured = Boolean(
    selectedSection && selectedBatch && selectedLevel && selectedSemester && selectedSection.batch_id === selectedBatch.id,
  );
  const moduleCatalogReady = Boolean((data.modules || []).some((item) => item.semester_number === Number(semester)));
  const classTypesReady = ["lecture", "tutorial", "practical"].every((required) =>
    (data["class-types"] || []).some((item) => item.name?.toLowerCase() === required),
  );
  const readiness = [
    ["Section configured", sectionConfigured],
    ["Courses available for this semester", moduleCatalogReady],
    ["Course Assignments cover this section", contextOfferings.length > 0],
    ["Teachers available", (data.teachers || []).length > 0],
    ["Rooms and blocks available", (data.rooms || []).length > 0 && (data.blocks || []).length > 0],
    ["Lecture, Tutorial, and Practical configured", classTypesReady],
    ["Time slots configured", (data["time-slots"] || []).length > 0],
  ];

  const previewReady = Boolean(intake && semester.trim() && section && file && supportedFile);
  const previewReason = !batchId
    ? "Select a batch before previewing."
    : !levelId
      ? "Select a level and intake before previewing."
      : !semesterId
        ? "Select a semester before previewing."
        : !section
        ? "Select a section before previewing."
        : !file || !supportedFile
          ? "Choose an Excel or CSV file."
          : "";
  const importReason = !preview
    ? "Preview the file before importing."
    : preview.invalid_rows > 0
      ? "Fix all validation errors before importing."
      : "";
  const url = `/api/v1/academic/sections/${section}/routine`;

  function resetPreview() {
    setPreview(null);
    setResult("");
  }

  async function check(event: FormEvent) {
    event.preventDefault();
    if (!previewReady || !file) return;
    setWorking("preview");
    setError("");
    setResult("");
    const body = new FormData();
    body.append("file", file);
    try {
      const endpoint = url + "/preview?intake_id=" + intake + "&semester_number=" + semester;
      const result = (await api.post(endpoint, body)).data;
      setPreview(result);
      const invalidRows = Number(result.invalid_rows || 0);
      notifySystemFeedback(invalidRows > 0
        ? { tone: "warning", title: "Routine preview found " + String(invalidRows) + " invalid row(s)", description: "Review the row numbers and reasons below, fix the file, then preview it again." }
        : { tone: "success", title: "Routine preview is ready", description: String(result.total_rows || 0) + " row(s) passed validation. Review the results before importing." });
    } catch (requestError: any) {
      const message = apiErrorMessage(requestError, "The file could not be previewed.");
      setError(message);
      notifySystemFeedback({ tone: "danger", title: "Routine preview failed", description: message });
    } finally {
      setWorking(null);
    }
  }

  async function submit() {
    if (!previewReady || !file || !preview || preview.invalid_rows > 0) return;
    setWorking("import");
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = (await api.post(`${url}/import?intake_id=${intake}&semester_number=${semester}`, body)).data;
      setResult(`Routine imported: ${response.success_count} successful, ${response.failed_count} failed, ${response.pending_section_references || 0} pending section reference(s).`);
      setPreview(null);
      setFile(null);
      if (input.current) input.current.value = "";
      const pendingResponse = await api.get(`/api/v1/academic/sections/${section}/routine/pending?intake_id=${intake}&semester_number=${semester}`);
      setPendingSections(pendingResponse.data);
    } catch (requestError: any) {
      const message = apiErrorMessage(requestError, "The routine could not be imported.");
      setError(message);
      notifySystemFeedback({ tone: "danger", title: "Routine import failed", description: message });
    } finally {
      setWorking(null);
    }
  }

  return <section className="mt-10 panel p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold">Import a section routine</h2>
        <p className="mt-1 text-sm text-slate-400">Preview validates the spreadsheet without writing. Import publishes valid rows to the canonical routine.</p>
      </div>
      {section && <div className="flex gap-2"><Button type="button" variant="outline" size="sm" onClick={() => downloadFile(`${url}/template?format=csv`, "section_routine_template.csv")}>CSV template</Button><Button type="button" variant="outline" size="sm" onClick={() => downloadFile(`${url}/template?format=xlsx`, "section_routine_template.xlsx")}>XLSX template</Button></div>}
    </div>

    <div className="mt-5 rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 text-sm">
      <p className="font-semibold text-blue-200">Before importing</p>
      <p className="mt-1 text-slate-300">Create the courses, active course assignments, lecturers, rooms, blocks, class types, and time slots referenced by the spreadsheet. The importer never creates these records from spreadsheet text.</p>
      <p className="mt-2 text-amber-200">Combined classes may reference sections that have not yet been created. The selected section must exist; other section memberships can be resolved later.</p>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">{setupLinks.map(([label, href]) => <Link key={href} href={href} className="interactive-link underline">{label}</Link>)}</div>
    </div>

    <form onSubmit={check} className="mt-6">
      <div className="grid gap-4 md:grid-cols-4">
        <label><span className="field-label">Batch</span><select required value={batchId} onChange={(event) => { setBatchId(event.target.value); setLevelId(""); setSemesterId(""); setSection(""); resetPreview(); }}><option value="">Select batch</option>{(data.batches || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label><span className="field-label">Level / Intake</span><select required disabled={!selectedBatch} value={levelId} onChange={(event) => { setLevelId(event.target.value); setSemesterId(""); setSection(""); resetPreview(); }}><option value="">Select level and intake</option>{levels.map((item) => <option key={item.id} value={item.id}>Level {item.level_number} · {item.intake_code}</option>)}</select></label>
        <label><span className="field-label">Semester</span><select required disabled={!selectedLevel} value={semesterId} onChange={(event) => { setSemesterId(event.target.value); setSection(""); resetPreview(); }}><option value="">Select semester</option>{semesters.map((item) => <option key={item.id} value={item.id}>{item.display_name || `Semester ${item.semester_number}`}</option>)}</select></label>
        <label><span className="field-label">Section</span><select required disabled={!selectedSemester} value={section} onChange={(event) => { setSection(event.target.value); resetPreview(); }}><option value="">{selectedSemester ? "Select section" : "Select Batch, Level / Intake, and Semester first"}</option>{eligibleSections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{selectedBatch && selectedSemester && !eligibleSections.length && <span className="mt-1 block text-sm text-amber-300">No sections have been created for this batch yet.</span>}</label>
      </div>

      {contextSelected && <div className="mt-4 flex flex-wrap gap-2 text-sm"><Badge tone={sectionConfigured ? "success" : "warning"}>{selectedProgram ? `${selectedProgram.name} / ` : ""}{selectedBatch?.name || "Batch not found"} / {selectedIntake?.name || "Intake not found"} / Semester {semester} / {selectedSection?.name || "Section not found"}</Badge></div>}

      <label className="mt-5 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-600 bg-slate-950/50 px-6 py-6 text-center transition hover:border-emerald-500 hover:bg-emerald-500/5 focus-within:ring-2 focus-within:ring-emerald-400">
        <span className="font-semibold text-slate-100">{file ? file.name : "Drop a routine CSV/XLSX here"}</span>
        <span className="mt-1 text-sm text-slate-400">{file ? `${Math.ceil(file.size / 1024)} KB selected` : "or choose a file from your device"}</span>
        <input ref={input} className="sr-only" type="file" accept=".csv,.xlsx" onChange={(event) => { setFile(event.target.files?.[0] ?? null); resetPreview(); }} />
      </label>
      {file && !supportedFile && <p className="mt-2 text-sm text-red-300" role="alert">Choose an Excel (.xlsx) or CSV (.csv) file.</p>}

      <div className="mt-5 flex flex-col items-end gap-2">
        <div className="flex flex-wrap justify-end gap-2"><Button type="submit" variant="secondary" loading={working === "preview"} disabled={!previewReady || working !== null} aria-describedby="preview-reason">{working === "preview" ? "Validating..." : "Preview import"}</Button><Button type="button" loading={working === "import"} disabled={!previewReady || !preview || preview.invalid_rows > 0 || working !== null} onClick={submit}>{working === "import" ? "Importing..." : "Import routine"}</Button></div>
        {!previewReady && <p id="preview-reason" className="text-right text-sm text-amber-300" role="status">{previewReason}</p>}
        {preview && !previewReady && <p className="text-right text-sm text-slate-400">Change the context or file and preview again before importing.</p>}
        {preview && preview.invalid_rows > 0 && <p className="text-right text-sm text-amber-300" role="status">{importReason}</p>}
        {!preview && previewReady && <p className="text-right text-sm text-slate-400" role="status">{importReason}</p>}
      </div>
    </form>

    <section className="mt-6 rounded-xl border border-slate-700 bg-slate-950/30 p-4" aria-labelledby="routine-readiness">
      <h3 id="routine-readiness" className="font-semibold">Routine setup readiness</h3>
      <p className="mt-1 text-sm text-slate-400">This is a master-data check for the selected context. Spreadsheet Preview remains the authoritative validation step.</p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">{readiness.map(([label, ready]) => <div key={String(label)} className="flex items-center gap-2 text-sm"><span className={`grid h-5 w-5 place-items-center rounded-full border ${ready ? "border-emerald-400 text-emerald-300" : contextSelected ? "border-amber-400 text-amber-300" : "border-slate-600 text-slate-500"}`} aria-hidden="true">{ready ? "OK" : contextSelected ? "!" : "-"}</span><span className={ready ? "text-slate-200" : "text-slate-400"}>{label}</span></div>)}</div>
    </section>

    {preview && <div className="mt-6 rounded-xl border border-slate-700 bg-slate-950/40 p-4" aria-live="polite">
      <div className="flex items-center justify-between gap-3"><h3 className="font-semibold">Validation preview</h3><Badge tone={preview.invalid_rows ? "warning" : "success"}>{preview.invalid_rows ? "Needs attention" : "Ready to import"}</Badge></div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-6">{[["Rows",preview.total_rows,"text-slate-100"],["New",preview.new_rows,"text-emerald-300"],["Existing",preview.existing_rows,"text-blue-300"],["Merged",preview.merge_rows,"text-amber-300"],["Pending sections",preview.pending_section_references || 0,"text-amber-200"],["Errors",preview.invalid_rows,"text-red-300"]].map(([label,value,tone]) => <div key={String(label)} className="rounded-lg bg-slate-900 p-3"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className={`mt-1 text-xl font-semibold ${tone}`}>{value}</p></div>)}</div>
      <div className="mt-4 max-h-72 overflow-auto table-wrap" role="region" aria-label="Scrollable records" tabIndex={0}><table><thead><tr><th>Row</th><th>Status</th><th>Details</th></tr></thead><tbody>{preview.rows?.map((item: any) => <tr key={`row-${item.row}`}><td>{item.row}</td><td><Badge tone={String(item.status).includes("pending") ? "warning" : "neutral"}>{String(item.status).replace("valid_", "").replaceAll("_", " ")}</Badge></td><td>{item.message}</td></tr>)}{preview.errors?.map((item: any) => <tr key={`error-${item.row_number}`}><td>{item.row_number}</td><td><Badge tone="danger">Error</Badge></td><td className="text-red-300">{item.error_message}</td></tr>)}</tbody></table></div>
    </div>}
    {pendingSections.length > 0 && <section className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4" aria-labelledby="pending-combined-sections">
      <h3 id="pending-combined-sections" className="font-semibold text-amber-200">Pending combined sections</h3>
      <p className="mt-1 text-sm text-slate-300">These references are stored safely and will resolve when the section exists and is included in the active course assignment.</p>
      <div className="mt-3 space-y-2">{pendingSections.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-950/50 px-3 py-2 text-sm"><span><span className="font-semibold text-amber-100">Pending section: {item.section_name}</span><span className="ml-2 text-slate-400">{item.module_code} · Routine #{item.routine_entry_id}</span></span><span className="text-slate-300">Action: create {item.section_name} or resolve later</span></div>)}</div>
    </section>}
    {result && <SystemFeedback className="mt-4" tone="success" title="Routine imported" description={result} />}
    {error && <SystemFeedback className="mt-4" tone="danger" title="Import could not be completed" description={error} />}
  </section>;
}
