'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useMemo, useState } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/PageHeader';

type Strategy = 'keep_existing' | 'whole_section' | 'random_balanced';
type Level = { id: number; batch_id: number; level_number: number; intake_code: string; intake_name: string | null };
type Batch = { id: number; name: string; start_date: string; end_date: string; levels: Level[] };
type Section = { id: number; name: string; batch_id: number };
type Semester = {
  id: number;
  batch_level_id: number;
  level_number: number;
  intake_id: number;
  intake_code: string;
  batch_id: number;
  batch_name: string;
  semester_number: number;
  start_date: string;
  end_date: string;
  status: string;
  calendar_uploaded: boolean;
  label: string;
};
type Student = { id: number; name: string | null; roll_number: string; section_id: number; section_name: string };
type Decision = {
  id: number;
  roll_number: string;
  name: string | null;
  source_section_id: number;
  target_section_id: number | null;
  action: string;
  reason: string | null;
};
type Preview = {
  total_students: number;
  promote_count?: number;
  assign_count?: number;
  hold_count: number;
  students: Decision[];
  errors: string[];
  preview_signature: string;
};
type Run = {
  id: number;
  intake_id: number;
  batch_id: number;
  from_cohort_semester_id: number;
  to_cohort_semester_id: number;
  effective_date: string;
  promoted_students: number;
  held_students: number;
};
type RunStudent = Decision & { promotion_run_item_id: number };
type History = { id: number; section_id: number; cohort_semester_id: number | null; starts_on: string; ends_on: string | null; status: string; promotion_run_id: number | null };

const fieldClass = 'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm';
const strategies: { value: Strategy; label: string }[] = [
  { value: 'keep_existing', label: 'Keep existing placement' },
  { value: 'whole_section', label: 'Whole-section mapping' },
  { value: 'random_balanced', label: 'Random balanced shuffle' },
];

function numericMap(values: Record<number, string>) {
  return Object.fromEntries(Object.entries(values).flatMap(([key, value]) => value ? [[Number(key), Number(value)]] : []));
}

export default function Page() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const [semesterForm, setSemesterForm] = useState({ batch_id: '', batch_level_id: '', semester_number: '', start_date: '', end_date: '' });

  const [placementSemesterId, setPlacementSemesterId] = useState('');
  const [placementStrategy, setPlacementStrategy] = useState<Strategy>('keep_existing');
  const [placementTargets, setPlacementTargets] = useState<number[]>([]);
  const [placementMapping, setPlacementMapping] = useState<Record<number, string>>({});
  const [placementOverrides, setPlacementOverrides] = useState<Record<number, string>>({});
  const [placementHolds, setPlacementHolds] = useState<number[]>([]);
  const [placementSeed, setPlacementSeed] = useState('0');
  const [placementPreview, setPlacementPreview] = useState<Preview | null>(null);
  const [placementDirty, setPlacementDirty] = useState(false);

  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [promotionStrategy, setPromotionStrategy] = useState<Strategy>('whole_section');
  const [promotionTargets, setPromotionTargets] = useState<number[]>([]);
  const [promotionMapping, setPromotionMapping] = useState<Record<number, string>>({});
  const [promotionOverrides, setPromotionOverrides] = useState<Record<number, string>>({});
  const [promotionHolds, setPromotionHolds] = useState<number[]>([]);
  const [promotionSeed, setPromotionSeed] = useState('0');
  const [promotionPreview, setPromotionPreview] = useState<Preview | null>(null);
  const [promotionDirty, setPromotionDirty] = useState(false);

  const [runStudents, setRunStudents] = useState<Record<number, RunStudent[]>>({});
  const [releaseTargets, setReleaseTargets] = useState<Record<string, string>>({});

  const [move, setMove] = useState({ student_id: '', cohort_semester_id: '', target_section_id: '', effective_date: '', reason: '' });
  const [history, setHistory] = useState<History[]>([]);

  async function load() {
    try {
      const responses = await Promise.all([
        api.get('/api/v1/academic/batches'),
        api.get('/api/v1/academic/sections'),
        api.get('/api/v1/academic/cohort-semesters'),
        api.get('/api/v1/academic/students'),
        api.get('/api/v1/academic/promotions'),
      ]);
      setBatches(responses[0].data);
      setSections(responses[1].data);
      setSemesters(responses[2].data);
      setStudents(responses[3].data);
      setRuns(responses[4].data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to load progression data.');
    }
  }

  useEffect(() => { void load(); }, []);

  const selectedBatch = batches.find((item) => item.id === Number(semesterForm.batch_id));
  const selectedLevel = selectedBatch?.levels.find((item) => item.id === Number(semesterForm.batch_level_id));
  const placementSemester = semesters.find((item) => item.id === Number(placementSemesterId));
  const source = semesters.find((item) => item.id === Number(sourceId));
  const target = semesters.find((item) => item.id === Number(targetId));
  const moveSemester = semesters.find((item) => item.id === Number(move.cohort_semester_id));
  const placementSections = useMemo(() => sections.filter((item) => item.batch_id === placementSemester?.batch_id), [sections, placementSemester]);
  const promotionSections = useMemo(() => sections.filter((item) => item.batch_id === target?.batch_id), [sections, target]);
  const moveSections = useMemo(() => sections.filter((item) => item.batch_id === moveSemester?.batch_id), [sections, moveSemester]);

  useEffect(() => {
    const ids = placementSections.map((item) => item.id);
    setPlacementTargets(ids);
    setPlacementMapping(Object.fromEntries(ids.map((id) => [id, String(id)])));
    setPlacementOverrides({});
    setPlacementHolds([]);
    setPlacementPreview(null);
    setPlacementDirty(false);
  }, [placementSemesterId, placementSections]);

  useEffect(() => {
    const ids = promotionSections.map((item) => item.id);
    setPromotionTargets(ids);
    setPromotionMapping(Object.fromEntries(ids.map((id) => [id, String(id)])));
    setPromotionOverrides({});
    setPromotionHolds([]);
    setPromotionPreview(null);
    setPromotionDirty(false);
  }, [sourceId, targetId, promotionSections]);

  function sectionLabel(id: number | null) {
    return id == null ? 'Held / unassigned' : sections.find((item) => item.id === id)?.name ?? `Section #${id}`;
  }

  function semesterLabel(item: Semester) {
    return `${item.batch_name} - Level ${item.level_number} / Semester ${item.semester_number} - ${item.intake_code}`;
  }

  function toggleId(values: number[], id: number) {
    if (values.includes(id)) return values.length === 1 ? values : values.filter((item) => item !== id);
    return [...values, id];
  }

  async function createSemester(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await api.post('/api/v1/academic/cohort-semesters', {
        batch_level_id: Number(semesterForm.batch_level_id),
        semester_number: Number(semesterForm.semester_number),
        start_date: semesterForm.start_date,
        end_date: semesterForm.end_date,
      });
      setMessage('Semester created. Upload its Academic Calendar PDF before assignment or progression.');
      setSemesterForm({ batch_id: '', batch_level_id: '', semester_number: '', start_date: '', end_date: '' });
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to create this Semester.');
    }
  }

  function placementPayload(signature?: string) {
    return {
      cohort_semester_id: Number(placementSemesterId),
      student_ids: [],
      placement_strategy: placementStrategy,
      target_section_ids: placementTargets,
      section_mapping: numericMap(placementMapping),
      manual_overrides: numericMap(placementOverrides),
      hold_student_ids: placementHolds,
      random_seed: Number(placementSeed) || 0,
      preview_signature: signature,
    };
  }

  async function previewPlacement(event?: FormEvent) {
    event?.preventDefault();
    try {
      setError('');
      const response = await api.post('/api/v1/academic/section-placements/preview', placementPayload());
      setPlacementPreview(response.data);
      setPlacementDirty(false);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Initial assignment preview failed.');
    }
  }

  async function applyPlacement() {
    if (!placementPreview || placementDirty || placementPreview.errors.length) return;
    try {
      const response = await api.post('/api/v1/academic/section-placements', placementPayload(placementPreview.preview_signature));
      setMessage(`${response.data.assign_count} students assigned; ${response.data.hold_count} held.`);
      setPlacementPreview(null);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Initial assignment failed.');
    }
  }

  function promotionPayload(signature?: string) {
    return {
      intake_id: source?.intake_id,
      batch_id: source?.batch_id,
      from_cohort_semester_id: source?.id,
      to_cohort_semester_id: target?.id,
      effective_date: target?.start_date,
      placement_strategy: promotionStrategy,
      target_section_ids: promotionTargets,
      section_mapping: numericMap(promotionMapping),
      manual_overrides: numericMap(promotionOverrides),
      hold_student_ids: promotionHolds,
      random_seed: Number(promotionSeed) || 0,
      preview_signature: signature,
    };
  }

  async function previewPromotion(event?: FormEvent) {
    event?.preventDefault();
    try {
      setError('');
      const response = await api.post('/api/v1/academic/promotions/preview', promotionPayload());
      setPromotionPreview(response.data);
      setPromotionDirty(false);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Progression preview failed.');
    }
  }

  async function applyPromotion() {
    if (!promotionPreview || promotionDirty || promotionPreview.errors.length) return;
    try {
      const response = await api.post('/api/v1/academic/promotions', promotionPayload(promotionPreview.preview_signature));
      setMessage(`Promotion run #${response.data.id} applied: ${response.data.promoted_students} progressed and ${response.data.held_students} held.`);
      setPromotionPreview(null);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Progression could not be applied.');
    }
  }

  async function showRunStudents(runId: number) {
    if (runStudents[runId]) {
      setRunStudents((current) => ({ ...current, [runId]: [] }));
      return;
    }
    try {
      const response = await api.get(`/api/v1/academic/promotions/${runId}/students`);
      setRunStudents((current) => ({ ...current, [runId]: response.data }));
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to load promotion decisions.');
    }
  }

  async function releaseHold(run: Run, studentId: number) {
    const key = `${run.id}:${studentId}`;
    const targetSectionId = Number(releaseTargets[key]);
    if (!targetSectionId) return;
    try {
      await api.post(`/api/v1/academic/promotions/${run.id}/students/${studentId}/release`, { target_section_id: targetSectionId, reason: 'Released by administrator' });
      setMessage('Held student released into the selected Section.');
      const response = await api.get(`/api/v1/academic/promotions/${run.id}/students`);
      setRunStudents((current) => ({ ...current, [run.id]: response.data }));
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to release this student.');
    }
  }

  async function loadHistory(studentId: string) {
    setMove((current) => ({ ...current, student_id: studentId }));
    if (!studentId) { setHistory([]); return; }
    try {
      setHistory((await api.get(`/api/v1/academic/students/${studentId}/academic-history`)).data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to load academic history.');
    }
  }

  async function moveStudent(event: FormEvent) {
    event.preventDefault();
    try {
      await api.post(`/api/v1/academic/students/${move.student_id}/section-moves`, {
        cohort_semester_id: Number(move.cohort_semester_id),
        target_section_id: Number(move.target_section_id),
        effective_date: move.effective_date,
        reason: move.reason || null,
      });
      setMessage('Student Section move recorded without overwriting earlier placement history.');
      await loadHistory(move.student_id);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to move this student.');
    }
  }

  const strategyControls = (
    strategy: Strategy,
    setStrategy: (value: Strategy) => void,
    targetSections: Section[],
    targetIds: number[],
    setTargetIds: (value: number[]) => void,
    mapping: Record<number, string>,
    setMapping: (value: Record<number, string>) => void,
    seed: string,
    setSeed: (value: string) => void,
    markDirty: () => void,
  ) => <div className='mt-4 grid gap-4 md:grid-cols-3'>
    <label><span className='field-label'>Placement strategy</span><select className={fieldClass} value={strategy} onChange={(event) => { setStrategy(event.target.value as Strategy); markDirty(); }}>{strategies.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
    <label><span className='field-label'>Shuffle seed</span><input className={fieldClass} type='number' value={seed} disabled={strategy !== 'random_balanced'} onChange={(event) => { setSeed(event.target.value); markDirty(); }} /></label>
    <fieldset><legend className='field-label'>Allowed target Sections</legend><div className='flex flex-wrap gap-3'>{targetSections.map((section) => <label key={section.id} className='flex items-center gap-2 text-sm'><input type='checkbox' checked={targetIds.includes(section.id)} onChange={() => { setTargetIds(toggleId(targetIds, section.id)); markDirty(); }} />{section.name}</label>)}</div></fieldset>
    {strategy === 'whole_section' && <fieldset className='md:col-span-3'><legend className='field-label'>Whole-section mapping</legend><div className='grid gap-3 md:grid-cols-3'>{targetSections.map((sourceSection) => <label key={sourceSection.id} className='flex items-center gap-2 text-sm'><span className='min-w-20'>{sourceSection.name} -&gt;</span><select className={fieldClass} value={mapping[sourceSection.id] ?? ''} onChange={(event) => { setMapping({ ...mapping, [sourceSection.id]: event.target.value }); markDirty(); }}><option value=''>Unmapped</option>{targetSections.filter((item) => targetIds.includes(item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>)}</div></fieldset>}
  </div>;

  const decisionTable = (
    preview: Preview,
    targetSections: Section[],
    holds: number[],
    setHolds: (value: number[]) => void,
    overrides: Record<number, string>,
    setOverrides: (value: Record<number, string>) => void,
    markDirty: () => void,
  ) => <div className='mt-5 overflow-x-auto' role="region" aria-label="Scrollable records" tabIndex={0}>
    <table><thead><tr><th>Hold</th><th>Student</th><th>From</th><th>Manual override</th><th>Previewed result</th></tr></thead><tbody>{preview.students.map((student) => <tr key={student.id}>
      <td><input aria-label={`Hold ${student.name ?? student.roll_number}`} type='checkbox' checked={holds.includes(student.id)} onChange={() => { setHolds(holds.includes(student.id) ? holds.filter((id) => id !== student.id) : [...holds, student.id]); markDirty(); }} /></td>
      <td>{student.name ?? student.roll_number}<div className='text-xs text-slate-500'>{student.roll_number}</div></td>
      <td>{sectionLabel(student.source_section_id)}</td>
      <td><select aria-label={`Section override for ${student.name ?? student.roll_number}`} className={fieldClass} value={overrides[student.id] ?? ''} onChange={(event) => { const next = { ...overrides }; if (event.target.value) next[student.id] = event.target.value; else delete next[student.id]; setOverrides(next); markDirty(); }}><option value=''>Use strategy</option>{targetSections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></td>
      <td>{sectionLabel(student.target_section_id)}{student.reason && <div className='text-xs text-slate-500'>{student.reason}</div>}</td>
    </tr>)}</tbody></table>
  </div>;

  return <div className='max-w-7xl'>
    <PageHeader title='Semester placement and progression' description='Intake setup creates the fixed semester pairs; use this page to assign students, progress them, and preserve history.' />
    {message && <p className='mb-4 text-sm text-emerald-400'>{message}</p>}
    {error && <p className='mb-4 text-sm text-red-400'>{error}</p>}

    <section className='panel p-5'>
      <h2 className='text-lg font-semibold'>Semester readiness</h2>
      <p className='mt-1 text-sm text-slate-400'>Semester records are created automatically with each Intake Code: Level 1 creates 1?2, Level 2 creates 3?4, and Level 3 creates 5?6.</p>
      <div className='mt-5 overflow-x-auto' role="region" aria-label="Scrollable records" tabIndex={0}><table><thead><tr><th>Semester</th><th>Dates</th><th>Calendar readiness</th></tr></thead><tbody>{semesters.map((item) => <tr key={item.id}><td>{semesterLabel(item)}</td><td>{item.start_date} to {item.end_date}</td><td>{item.calendar_uploaded ? <span className='text-emerald-400'>PDF uploaded</span> : <Link className='text-amber-300 underline' href='/admin/academic/semester-resources'>Upload required PDF</Link>}</td></tr>)}</tbody></table></div>
    </section>

    <section className='panel mt-7 p-5'>
      <h2 className='text-lg font-semibold'>1. Initial student assignment</h2>
      <p className='mt-1 text-sm text-slate-400'>Bulk-assign students not yet placed in the Semester. A calendar PDF is required.</p>
      <form onSubmit={previewPlacement}>
        <select aria-label='Initial assignment semester' className={`${fieldClass} mt-4 max-w-xl`} required value={placementSemesterId} onChange={(event) => setPlacementSemesterId(event.target.value)}><option value=''>Target Semester</option>{semesters.map((item) => <option key={item.id} value={item.id}>{semesterLabel(item)}</option>)}</select>
        {placementSemester && strategyControls(placementStrategy, setPlacementStrategy, placementSections, placementTargets, setPlacementTargets, placementMapping, setPlacementMapping, placementSeed, setPlacementSeed, () => setPlacementDirty(true))}
        <div className='mt-4'><Button type='submit'>Preview initial assignment</Button></div>
      </form>
      {placementPreview && <div className='mt-5 rounded-xl border border-slate-800 p-4'><div className='flex flex-wrap items-center gap-4'><span>{placementPreview.total_students} students</span><span className='text-emerald-400'>{placementPreview.assign_count} assign</span><span className='text-amber-300'>{placementPreview.hold_count} hold</span><Button type='button' disabled={placementDirty || Boolean(placementPreview.errors.length)} onClick={() => void applyPlacement()}>Apply assignment</Button></div>{placementDirty && <p className='mt-2 text-sm text-amber-300'>Choices changed; preview again before applying.</p>}{placementPreview.errors.map((item) => <p key={item} className='mt-2 text-sm text-red-400'>{item}</p>)}{decisionTable(placementPreview, placementSections, placementHolds, setPlacementHolds, placementOverrides, setPlacementOverrides, () => setPlacementDirty(true))}</div>}
    </section>

    <section className='panel mt-7 p-5'>
      <h2 className='text-lg font-semibold'>2. Semester / Level progression</h2>
      <p className='mt-1 text-sm text-slate-400'>Allowed paths are 1 to 2, 2 to 3, 3 to 4, 4 to 5, and 5 to 6. Cross-Level transitions require the next Level Intake Code.</p>
      <form onSubmit={previewPromotion}>
        <div className='mt-4 grid gap-3 md:grid-cols-2'>
          <select aria-label='Source semester' className={fieldClass} required value={sourceId} onChange={(event) => { setSourceId(event.target.value); setTargetId(''); }}><option value=''>Source Semester</option>{semesters.filter((item) => item.semester_number < 6).map((item) => <option key={item.id} value={item.id}>{semesterLabel(item)}</option>)}</select>
          <select aria-label='Target semester' className={fieldClass} required value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value=''>Target Semester</option>{semesters.filter((item) => source && item.batch_id === source.batch_id && item.semester_number === source.semester_number + 1).map((item) => <option key={item.id} value={item.id}>{semesterLabel(item)}{item.calendar_uploaded ? '' : ' - PDF missing'}</option>)}</select>
        </div>
        {target && strategyControls(promotionStrategy, setPromotionStrategy, promotionSections, promotionTargets, setPromotionTargets, promotionMapping, setPromotionMapping, promotionSeed, setPromotionSeed, () => setPromotionDirty(true))}
        <div className='mt-4'><Button type='submit'>Preview progression</Button></div>
      </form>
      {promotionPreview && <div className='mt-5 rounded-xl border border-slate-800 p-4'><div className='flex flex-wrap items-center gap-4'><span>{promotionPreview.total_students} students</span><span className='text-emerald-400'>{promotionPreview.promote_count} progress</span><span className='text-amber-300'>{promotionPreview.hold_count} hold</span><Button type='button' disabled={promotionDirty || Boolean(promotionPreview.errors.length)} onClick={() => void applyPromotion()}>Apply progression</Button></div>{promotionDirty && <p className='mt-2 text-sm text-amber-300'>Choices changed; preview again before applying.</p>}{promotionPreview.errors.map((item) => <p key={item} className='mt-2 text-sm text-red-400'>{item}</p>)}{decisionTable(promotionPreview, promotionSections, promotionHolds, setPromotionHolds, promotionOverrides, setPromotionOverrides, () => setPromotionDirty(true))}</div>}
    </section>

    <section className='panel mt-7 p-5'>
      <h2 className='text-lg font-semibold'>3. Promotion history and held students</h2>
      <div className='mt-4 space-y-3'>{runs.map((run) => {
        const runTarget = semesters.find((item) => item.id === run.to_cohort_semester_id);
        const targets = sections.filter((item) => item.batch_id === runTarget?.batch_id);
        return <div key={run.id} className='rounded-xl border border-slate-800 p-4'><div className='flex flex-wrap items-center justify-between gap-3'><div><strong>Run #{run.id}</strong> - {run.from_cohort_semester_id} to {run.to_cohort_semester_id} on {run.effective_date}<div className='text-sm text-slate-400'>{run.promoted_students} progressed; {run.held_students} held</div></div><Button type='button' size='sm' variant='ghost' onClick={() => void showRunStudents(run.id)}>{runStudents[run.id]?.length ? 'Hide decisions' : 'View decisions'}</Button></div>{runStudents[run.id]?.length ? <div className='mt-3 overflow-x-auto' role="region" aria-label="Scrollable records" tabIndex={0}><table><thead><tr><th>Student</th><th>Decision</th><th>From</th><th>To / release</th></tr></thead><tbody>{runStudents[run.id].map((student) => { const key = `${run.id}:${student.id}`; return <tr key={student.id}><td>{student.name ?? student.roll_number}<div className='text-xs text-slate-500'>{student.roll_number}</div></td><td className='capitalize'>{student.action}</td><td>{sectionLabel(student.source_section_id)}</td><td>{student.action === 'hold' ? <div className='flex gap-2'><select aria-label={`Release section for ${student.name ?? student.roll_number}`} className={fieldClass} value={releaseTargets[key] ?? ''} onChange={(event) => setReleaseTargets({ ...releaseTargets, [key]: event.target.value })}><option value=''>Target Section</option>{targets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><Button type='button' size='sm' onClick={() => void releaseHold(run, student.id)}>Release</Button></div> : sectionLabel(student.target_section_id)}</td></tr>; })}</tbody></table></div> : null}</div>;
      })}{!runs.length && <p className='text-sm text-slate-400'>No promotion runs yet.</p>}</div>
    </section>

    <section className='panel mt-7 p-5'>
      <h2 className='text-lg font-semibold'>4. Individual Section move and placement history</h2>
      <form onSubmit={moveStudent} className='mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5'>
        <select aria-label='Student to move' className={fieldClass} required value={move.student_id} onChange={(event) => void loadHistory(event.target.value)}><option value=''>Student</option>{students.map((item) => <option key={item.id} value={item.id}>{item.roll_number} - {item.name}</option>)}</select>
        <select aria-label='Placement semester' className={fieldClass} required value={move.cohort_semester_id} onChange={(event) => setMove({ ...move, cohort_semester_id: event.target.value, target_section_id: '', effective_date: '' })}><option value=''>Semester</option>{semesters.map((item) => <option key={item.id} value={item.id}>{semesterLabel(item)}</option>)}</select>
        <select aria-label='Destination section' className={fieldClass} required value={move.target_section_id} onChange={(event) => setMove({ ...move, target_section_id: event.target.value })}><option value=''>Target Section</option>{moveSections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <input className={fieldClass} required type='date' aria-label='Move effective date' min={moveSemester?.start_date} max={moveSemester?.end_date} value={move.effective_date} onChange={(event) => setMove({ ...move, effective_date: event.target.value })} />
        <Button type='submit'>Move student</Button>
      </form>
      {history.length ? <div className='mt-5 overflow-x-auto' role="region" aria-label="Scrollable records" tabIndex={0}><table><thead><tr><th>Semester</th><th>Section</th><th>Starts</th><th>Ends</th><th>Status</th><th>Run</th></tr></thead><tbody>{history.map((item) => <tr key={item.id}><td>{item.cohort_semester_id ? `Semester record #${item.cohort_semester_id}` : 'Legacy placement'}</td><td>{sectionLabel(item.section_id)}</td><td>{item.starts_on}</td><td>{item.ends_on ?? 'Current'}</td><td className='capitalize'>{item.status}</td><td>{item.promotion_run_id ?? '-'}</td></tr>)}</tbody></table></div> : move.student_id ? <p className='mt-4 text-sm text-slate-400'>No placement history recorded.</p> : null}
    </section>
  </div>;
}
