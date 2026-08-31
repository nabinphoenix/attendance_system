"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState, LoadingState } from "@/components/ui/States";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type Student = { id: number; name: string; email: string; section_id: number; section_name: string; has_account: boolean; account_status: string };
type Section = { id: number; name: string; intake_id: number | null };
type Intake = { id: number; name: string; code: string };

export default function StudentInvitationPanel() {
  const [students, setStudents] = useState<Student[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [intakes, setIntakes] = useState<Intake[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [onlyUnregistered, setOnlyUnregistered] = useState(true);
  const [intakeId, setIntakeId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError("");
    setStudents([]);
    setSelected([]);
    try {
      const params = new URLSearchParams({ only_without_accounts: String(onlyUnregistered) });
      if (intakeId) params.set("intake_id", intakeId);
      if (sectionId) params.set("section_id", sectionId);
      const response = await api.get(`/api/v1/academic/students?${params.toString()}`);
      if (sequence !== requestSequence.current) return;
      setStudents(response.data);
      setSelected((current) => current.filter((id) => response.data.some((student: Student) => student.id === id)));
    } catch (requestError: any) {
      if (sequence !== requestSequence.current) return;
      setError(requestError.response?.data?.detail ?? "Unable to load students.");
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [intakeId, onlyUnregistered, sectionId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    Promise.all([api.get<Section[]>("/api/v1/academic/sections"), api.get<Intake[]>("/api/v1/academic/intakes")])
      .then(([sectionResponse, intakeResponse]) => { setSections(sectionResponse.data); setIntakes(intakeResponse.data); })
      .catch(() => { setSections([]); setIntakes([]); });
  }, []);

  const visibleSections = useMemo(
    () => intakeId ? sections.filter((section) => section.intake_id === Number(intakeId)) : sections,
    [intakeId, sections],
  );

  const targets = useMemo(
    () => selected.length ? selected : students.map((student) => student.id),
    [selected, students],
  );
  const targetStudents = useMemo(
    () => students.filter((student) => targets.includes(student.id)),
    [students, targets],
  );
  const passwordSetupCount = targetStudents.filter((student) => student.has_account).length;
  const activationCount = targetStudents.length - passwordSetupCount;
  const allSelected = students.length > 0 && selected.length === students.length;
  const selectionText = selected.length ? `${selected.length} selected` : `All ${students.length} shown`;

  const toggle = (id: number) => setSelected((current) => current.includes(id)
    ? current.filter((value) => value !== id)
    : [...current, id]);
  const toggleAll = () => setSelected(allSelected ? [] : students.map((student) => student.id));

  async function send() {
    if (!targets.length) return;
    setSending(true);
    setError("");
    try {
      const response = await api.post("/api/v1/academic/students/invitations", {
        student_ids: targets,
        intake_id: intakeId ? Number(intakeId) : null,
        section_id: sectionId ? Number(sectionId) : null,
        only_without_accounts: onlyUnregistered,
      });
      setSummary(`Account emails queued: ${response.data.sent} (${response.data.activation_sent} activation, ${response.data.password_setup_sent} password setup), ${response.data.failed} failed. The delivery worker processes the selected emails automatically.`);
      setSelected([]);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to send invitations.");
    } finally {
      setSending(false);
      setConfirmOpen(false);
    }
  }

  const requestSend = () => setConfirmOpen(true);

  return <section className="mt-8 panel overflow-hidden">
    <div className="border-b border-slate-800 p-4 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-emerald-400">Student onboarding</p>
          <h2 className="mt-1 text-xl font-semibold">Send account setup emails</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">Send activation links to new profiles and secure password-setup links to existing accounts.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-300">
            <span className="sr-only">Filter by intake</span>
            <select value={intakeId} onChange={(event) => { setIntakeId(event.target.value); setSectionId(""); setSelected([]); }} className="min-w-36 border-0 bg-transparent p-0 text-sm focus:ring-0">
              <option value="">All intakes</option>
              {intakes.map((intake) => <option key={intake.id} value={intake.id}>{intake.code} — {intake.name}</option>)}
            </select>
          </label>
          <label className="flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-300">
            <span className="sr-only">Filter by section</span>
            <select value={sectionId} onChange={(event) => { setSectionId(event.target.value); setSelected([]); }} className="min-w-36 border-0 bg-transparent p-0 text-sm focus:ring-0">
              <option value="">All sections</option>
              {visibleSections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
            </select>
          </label>
          <button type="button" role="switch" aria-checked={onlyUnregistered} onClick={() => setOnlyUnregistered((value) => !value)} className={`inline-flex min-h-10 items-center justify-between gap-3 rounded-lg border px-3 text-sm font-medium transition ${onlyUnregistered ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-200" : "border-slate-700 bg-slate-950 text-slate-300"}`}>
            <span>Unregistered only</span><span aria-hidden="true" className={`h-5 w-9 rounded-full p-0.5 transition ${onlyUnregistered ? "bg-emerald-400" : "bg-slate-700"}`}><span className={`block h-4 w-4 rounded-full bg-white transition ${onlyUnregistered ? "translate-x-4" : "translate-x-0"}`} /></span>
          </button>
          <Button loading={sending} disabled={!targets.length || loading} onClick={requestSend} className="w-full sm:w-auto">{selected.length ? `Email ${selected.length} selected` : "Email all shown"}</Button>
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-3 rounded-lg bg-slate-950/60 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-400"><span className="font-semibold text-slate-200">{selectionText}</span> · Leave every row unselected to invite all matching students.</p>
        <Button type="button" variant="ghost" size="sm" disabled={!students.length || loading} onClick={toggleAll}>{allSelected ? "Clear selection" : "Select all"}</Button>
      </div>
    </div>

    {summary && <SystemFeedback className="mx-4 mt-4 sm:mx-6" tone="success" title="Account emails queued" description={summary} />}
    {error && <SystemFeedback className="mx-4 mt-4 sm:mx-6" tone="danger" title="Unable to send account emails" description={error} />}

    <div className="p-4 sm:p-6">
      {loading ? <LoadingState label="Loading students" /> : !students.length ? <EmptyState title="No matching students" description="There are no students waiting for an invitation." /> : <>
        <div className="grid gap-3 md:hidden">{students.map((student) => {
          const checked = selected.includes(student.id);
          return <label key={student.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${checked ? "border-emerald-500/60 bg-emerald-500/10" : "border-slate-800 bg-slate-950/45"}`}>
            <input aria-label={`Select ${student.name}`} type="checkbox" checked={checked} onChange={() => toggle(student.id)} className="mt-1" />
            <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center justify-between gap-2"><span className="truncate font-semibold text-slate-100">{student.name}</span><StatusBadge status={student.account_status} /></span><span className="mt-1 block break-all text-sm text-slate-400">{student.email}</span><span className="mt-1 block text-xs text-slate-500">Section {student.section_name}</span></span>
          </label>;
        })}</div>
        <div className="hidden md:block table-wrap"><table><thead><tr><th><input aria-label="Select all students" type="checkbox" checked={allSelected} onChange={toggleAll} /></th><th>Name</th><th>Email</th><th>Section</th><th>Status</th></tr></thead><tbody>{students.map((student) => <tr key={student.id}><td><input aria-label={`Select ${student.name}`} type="checkbox" checked={selected.includes(student.id)} onChange={() => toggle(student.id)} /></td><td className="font-medium text-slate-100">{student.name}</td><td>{student.email}</td><td>{student.section_name}</td><td><StatusBadge status={student.account_status} /></td></tr>)}</tbody></table></div>
      </>}
    </div>
    <ConfirmDialog open={confirmOpen} title={`Email ${targets.length} student${targets.length === 1 ? "" : "s"}?`} description={`${activationCount} activation link${activationCount === 1 ? "" : "s"} and ${passwordSetupCount} secure password-setup link${passwordSetupCount === 1 ? "" : "s"} will be queued. A password changes only when the student opens the link and saves a new one.`} confirmLabel="Send account emails" onClose={() => setConfirmOpen(false)} onConfirm={send} />
  </section>;
}
