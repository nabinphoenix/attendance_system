'use client';

import { type FormEvent, useEffect, useMemo, useState } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/Button';

type Option = { id: number; name?: string; code?: string };
type Section = { id: number; name: string; batch_id: number; intake_id: number | null; semester_number: number | null };
type Cohort = { id: number; intake_id: number; batch_id: number; semester_number: number; attempt_number: number; start_date: string; end_date: string; status: string };
type Row = { id: number; roll_number: string; name: string | null; source_section_id: number; target_section_id: number | null; action: string };
type Preview = { source: Cohort; target: Cohort; total_students: number; promote_count: number; hold_count: number; students: Row[]; errors: string[] };
type Run = { id: number; intake_id: number; batch_id: number; from_cohort_semester_id: number; to_cohort_semester_id: number; effective_date: string; promoted_students: number; held_students: number };

const fieldClass = 'rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm';

export default function Page() {
  const [intakes, setIntakes] = useState<Option[]>([]);
  const [batches, setBatches] = useState<Option[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [mapping, setMapping] = useState<Record<number, string>>({});
  const [holdIds, setHoldIds] = useState<number[]>([]);
  const [previewDirty, setPreviewDirty] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [setup, setSetup] = useState({ intake_id: '', batch_id: '', semester_number: '', start_date: '', end_date: '' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function load() {
    try {
      const responses = await Promise.all([
        api.get('/api/v1/academic/intakes'),
        api.get('/api/v1/academic/batches'),
        api.get('/api/v1/academic/sections'),
        api.get('/api/v1/academic/cohort-semesters'),
        api.get('/api/v1/academic/promotions'),
      ]);
      setIntakes(responses[0].data);
      setBatches(responses[1].data);
      setSections(responses[2].data);
      setCohorts(responses[3].data);
      setRuns(responses[4].data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to load promotion setup.');
    }
  }

  useEffect(() => { void load(); }, []);

  const source = cohorts.find((item) => item.id === Number(sourceId));
  const target = cohorts.find((item) => item.id === Number(targetId));
  const sourceSections = useMemo(() => source
    ? sections.filter((section) => section.batch_id === source.batch_id
      && (section.intake_id === null || section.intake_id === source.intake_id)
      && (section.semester_number === null || section.semester_number === source.semester_number))
    : [], [sections, source]);
  const targetSections = useMemo(() => target
    ? sections.filter((section) => section.batch_id === target.batch_id
      && section.intake_id === target.intake_id
      && section.semester_number === target.semester_number)
    : [], [sections, target]);

  useEffect(() => {
    const defaults: Record<number, string> = {};
    sourceSections.forEach((sourceSection) => {
      const match = targetSections.find((item) => item.name.toLowerCase() === sourceSection.name.toLowerCase());
      if (match) defaults[sourceSection.id] = String(match.id);
    });
    setMapping(defaults);
    setHoldIds([]);
    setPreview(null);
    setPreviewDirty(false);
  }, [sourceSections, targetSections]);

  function payload() {
    return {
      intake_id: source?.intake_id,
      batch_id: source?.batch_id,
      from_cohort_semester_id: source?.id,
      to_cohort_semester_id: target?.id,
      effective_date: target?.start_date,
      section_mapping: Object.fromEntries(Object.entries(mapping).filter(([, value]) => value).map(([key, value]) => [Number(key), Number(value)])),
      hold_student_ids: holdIds,
    };
  }

  async function previewPromotion(event: FormEvent) {
    event.preventDefault();
    if (!source || !target) {
      setError('Select a source semester and its next semester.');
      return;
    }
    try {
      setError('');
      setMessage('');
      setPreview((await api.post('/api/v1/academic/promotions/preview', payload())).data);
      setPreviewDirty(false);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Promotion preview failed.');
    }
  }

  async function applyPromotion() {
    if (!preview || preview.errors.length || previewDirty) return;
    try {
      const result = (await api.post('/api/v1/academic/promotions', payload())).data as Run;
      setMessage('Promotion run #' + result.id + ' applied: ' + result.promoted_students + ' promoted and ' + result.held_students + ' held.');
      setPreview(null);
      setHoldIds([]);
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Promotion could not be applied.');
    }
  }

  async function createCohortSemester(event: FormEvent) {
    event.preventDefault();
    try {
      await api.post('/api/v1/academic/cohort-semesters', {
        ...setup,
        intake_id: Number(setup.intake_id),
        batch_id: Number(setup.batch_id),
        semester_number: Number(setup.semester_number),
      });
      setMessage('Cohort semester created.');
      setSetup({ intake_id: '', batch_id: '', semester_number: '', start_date: '', end_date: '' });
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Cohort semester could not be created.');
    }
  }

  const intakeLabel = (id: number) => {
    const item = intakes.find((option) => option.id === id);
    return item ? (item.code ?? item.name ?? String(id)) : 'Intake #' + id;
  };
  const batchLabel = (id: number) => batches.find((item) => item.id === id)?.name ?? 'Batch #' + id;
  const sectionLabel = (id: number | null) => sections.find((item) => item.id === id)?.name ?? 'Unmapped';

  return <div className='max-w-7xl'>
    <h1 className='mb-2 text-3xl font-bold'>Semester promotions</h1>
    <p className='mb-6 max-w-3xl text-slate-400'>Define dated semester windows, preview the exact roster, map sections, hold exceptions, and apply one auditable transition. Different intakes can run in the same semester number.</p>
    {message && <p className='mb-4 text-emerald-400'>{message}</p>}
    {error && <p className='mb-4 text-red-400'>{error}</p>}

    <section className='mb-8 rounded-xl border border-slate-800 bg-slate-900 p-5'>
      <h2 className='text-xl font-semibold'>Create a cohort semester window</h2>
      <p className='mt-1 text-sm text-slate-400'>The target semester starts on the promotion date.</p>
      <form onSubmit={createCohortSemester} className='mt-4 grid gap-3 md:grid-cols-5'>
        <select className={fieldClass} required value={setup.intake_id} onChange={(event) => setSetup({ ...setup, intake_id: event.target.value })}><option value=''>Intake</option>{intakes.map((item) => <option key={item.id} value={item.id}>{item.code ?? item.name}</option>)}</select>
        <select className={fieldClass} required value={setup.batch_id} onChange={(event) => setSetup({ ...setup, batch_id: event.target.value })}><option value=''>Batch</option>{batches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <input className={fieldClass} required min='1' type='number' placeholder='Semester' value={setup.semester_number} onChange={(event) => setSetup({ ...setup, semester_number: event.target.value })} />
        <input className={fieldClass} required type='date' value={setup.start_date} onChange={(event) => setSetup({ ...setup, start_date: event.target.value })} />
        <div className='flex gap-2'><input className={fieldClass + ' min-w-0 flex-1'} required type='date' value={setup.end_date} onChange={(event) => setSetup({ ...setup, end_date: event.target.value })} /><Button type='submit'>Add</Button></div>
      </form>
    </section>

    <section className='mb-8 rounded-xl border border-slate-800 bg-slate-900 p-5'>
      <h2 className='text-xl font-semibold'>Preview and apply promotion</h2>
      <form onSubmit={previewPromotion} className='mt-4 grid gap-3 md:grid-cols-3'>
        <select className={fieldClass} required value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value=''>Source semester</option>{cohorts.map((item) => <option key={item.id} value={item.id}>{intakeLabel(item.intake_id)} · {batchLabel(item.batch_id)} · Sem {item.semester_number} · {item.start_date} to {item.end_date}</option>)}</select>
        <select className={fieldClass} required value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value=''>Target semester</option>{cohorts.filter((item) => source && item.intake_id === source.intake_id && item.batch_id === source.batch_id && item.semester_number === source.semester_number + 1).map((item) => <option key={item.id} value={item.id}>Sem {item.semester_number} · {item.start_date} to {item.end_date}</option>)}</select>
        <Button type='submit'>Preview roster</Button>
      </form>
      {source && target && <div className='mt-5 rounded-lg border border-slate-800 p-4'><h3 className='font-semibold'>Section mapping</h3><p className='mt-1 text-sm text-slate-400'>Same-named sections are prefilled; change rows where needed.</p><div className='mt-3 grid gap-3 md:grid-cols-2'>{sourceSections.map((sourceSection) => <label key={sourceSection.id} className='flex items-center gap-3 text-sm'><span className='min-w-24'>{sourceSection.name}</span><span className='text-slate-500'>→</span><select className={fieldClass + ' flex-1'} value={mapping[sourceSection.id] ?? ''} onChange={(event) => { setMapping({ ...mapping, [sourceSection.id]: event.target.value }); setPreviewDirty(true); }}><option value=''>No target section</option>{targetSections.map((targetSection) => <option key={targetSection.id} value={targetSection.id}>{targetSection.name}</option>)}</select></label>)}</div></div>}
      {preview && <div className='mt-5 rounded-lg border border-slate-700 p-4'><div className='flex flex-wrap items-center gap-4'><span>{preview.total_students} source students</span><span className='text-emerald-400'>{preview.promote_count} promote</span><span className='text-amber-300'>{preview.hold_count} hold</span><Button disabled={Boolean(preview.errors.length) || previewDirty} onClick={() => void applyPromotion()}>Apply promotion</Button></div>{previewDirty && <p className='mt-2 text-sm text-amber-300'>The decision changed. Preview again before applying.</p>}{preview.errors.map((item) => <p key={item} className='mt-2 text-sm text-red-400'>{item}</p>)}<div className='mt-4 overflow-x-auto'><table className='w-full text-left text-sm'><thead><tr className='border-b border-slate-700 text-slate-400'><th className='p-2'>Hold</th><th className='p-2'>Student</th><th className='p-2'>Source</th><th className='p-2'>Target</th><th className='p-2'>Decision</th></tr></thead><tbody>{preview.students.map((student) => <tr key={student.id} className='border-b border-slate-800'><td className='p-2'><input type='checkbox' checked={holdIds.includes(student.id)} onChange={(event) => { setHoldIds((current) => event.target.checked ? [...current, student.id] : current.filter((id) => id !== student.id)); setPreviewDirty(true); }} /></td><td className='p-2'>{student.name ?? student.roll_number} <span className='text-slate-500'>({student.roll_number})</span></td><td className='p-2'>{sectionLabel(student.source_section_id)}</td><td className='p-2'>{sectionLabel(student.target_section_id)}</td><td className='p-2 capitalize'>{student.action}</td></tr>)}</tbody></table></div></div>}
    </section>

    <section className='rounded-xl border border-slate-800 bg-slate-900 p-5'><h2 className='text-xl font-semibold'>Promotion history</h2><div className='mt-3 overflow-x-auto'><table className='w-full text-left text-sm'><thead><tr className='border-b border-slate-700 text-slate-400'><th className='p-2'>Effective</th><th className='p-2'>Intake / batch</th><th className='p-2'>Transition</th><th className='p-2'>Result</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id} className='border-b border-slate-800'><td className='p-2'>{run.effective_date}</td><td className='p-2'>{intakeLabel(run.intake_id)} · {batchLabel(run.batch_id)}</td><td className='p-2'>{run.from_cohort_semester_id} → {run.to_cohort_semester_id}</td><td className='p-2'>{run.promoted_students} promoted · {run.held_students} held</td></tr>)}</tbody></table>{!runs.length && <p className='py-5 text-center text-slate-400'>No promotion runs yet.</p>}</div></section>
  </div>;
}
