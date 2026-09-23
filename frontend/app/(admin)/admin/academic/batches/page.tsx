'use client';

import { type FormEvent, useEffect, useState } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { PageHeader } from '@/components/ui/PageHeader';

type Program = { id: number; name: string };
type Level = { id: number; level_number: number; intake_code: string; intake_name: string | null };
type Batch = {
  id: number;
  name: string;
  program_id: number;
  start_date: string;
  end_date: string;
  levels: Level[];
};
type LevelDraft = { level_number: number; intake_code: string; intake_name: string };
type BatchDraft = {
  name: string;
  program_id: string;
  start_date: string;
  end_date: string;
  levels: LevelDraft[];
};

const blankLevels = (): LevelDraft[] => [1, 2, 3].map((level_number) => ({
  level_number,
  intake_code: '',
  intake_name: '',
}));
const blank = (): BatchDraft => ({
  name: '',
  program_id: '',
  start_date: '',
  end_date: '',
  levels: blankLevels(),
});

function threeYearEnd(start: string) {
  if (!start) return '';
  const value = new Date(`${start}T00:00:00Z`);
  value.setUTCFullYear(value.getUTCFullYear() + 3);
  value.setUTCDate(value.getUTCDate() - 1);
  return value.toISOString().slice(0, 10);
}

export default function Page() {
  const [programs, setPrograms] = useState<Program[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [form, setForm] = useState<BatchDraft>(blank());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load() {
    try {
      const [programResponse, batchResponse] = await Promise.all([
        api.get('/api/v1/academic/programs'),
        api.get('/api/v1/academic/batches'),
      ]);
      setPrograms(programResponse.data);
      setBatches(batchResponse.data);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to load Batch configuration.');
    }
  }

  useEffect(() => { void load(); }, []);

  function changeStart(start_date: string) {
    setForm((current) => ({ ...current, start_date, end_date: threeYearEnd(start_date) }));
  }

  function changeLevel(index: number, values: Partial<LevelDraft>) {
    setForm((current) => ({
      ...current,
      levels: current.levels.map((level, itemIndex) => itemIndex === index ? { ...level, ...values } : level),
    }));
  }

  function startEdit(batch: Batch) {
    setEditingId(batch.id);
    setError('');
    setMessage('');
    setForm({
      name: batch.name,
      program_id: String(batch.program_id),
      start_date: batch.start_date,
      end_date: batch.end_date,
      levels: [1, 2, 3].map((number) => {
        const level = batch.levels.find((item) => item.level_number === number);
        return {
          level_number: number,
          intake_code: level?.intake_code ?? '',
          intake_name: level?.intake_name ?? '',
        };
      }),
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(blank());
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      if (editingId == null) {
        await api.post('/api/v1/academic/batches', {
          ...form,
          program_id: Number(form.program_id),
          levels: form.levels.map((level) => ({
            ...level,
            intake_code: level.intake_code.trim(),
            intake_name: level.intake_name.trim() || null,
          })),
        });
        setMessage('Three-year Batch and Levels 1-3 created.');
      } else {
        const batch = batches.find((item) => item.id === editingId)!;
        await api.patch(`/api/v1/academic/batches/${editingId}`, {
          name: form.name,
          start_date: form.start_date,
          end_date: form.end_date,
        });
        await Promise.all(batch.levels.map((level) => {
          const draft = form.levels.find((item) => item.level_number === level.level_number)!;
          return api.patch(`/api/v1/academic/levels/${level.id}`, {
            intake_code: draft.intake_code.trim(),
            intake_name: draft.intake_name.trim() || null,
          });
        }));
        setMessage('Batch and Level Intake Codes updated.');
      }
      cancelEdit();
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to save this Batch.');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (deleteId == null) return;
    try {
      await api.delete(`/api/v1/academic/batches/${deleteId}`);
      setMessage('Batch deleted.');
      await load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? 'Unable to delete this Batch.');
    } finally {
      setDeleteId(null);
    }
  }

  const programName = (id: number) => programs.find((item) => item.id === id)?.name ?? `Program #${id}`;

  return <div className='max-w-7xl'>
    <PageHeader
      title='Three-year Batches'
      description='A Batch owns permanent Sections and exactly three Levels. Each Level has its own required Intake Code.'
    />
    {message && <p className='mb-4 text-sm text-emerald-400'>{message}</p>}
    {error && <p className='mb-4 text-sm text-red-400'>{error}</p>}

    <section className='panel p-5'>
      <h2 className='text-lg font-semibold'>{editingId == null ? 'Create Batch' : 'Edit Batch'}</h2>
      <p className='mt-1 text-sm text-slate-400'>The end date is fixed to three years minus one day from the start date.</p>
      <form onSubmit={submit} className='mt-5 grid gap-4'>
        <div className='grid gap-4 md:grid-cols-4'>
          <label><span className='field-label'>Batch name</span><input className='w-full' required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          <label><span className='field-label'>Program</span><select className='w-full' required disabled={editingId != null} value={form.program_id} onChange={(event) => setForm({ ...form, program_id: event.target.value })}><option value=''>Select program</option>{programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}</select></label>
          <label><span className='field-label'>Start date</span><input className='w-full' required type='date' value={form.start_date} onChange={(event) => changeStart(event.target.value)} /></label>
          <label><span className='field-label'>End date</span><input className='w-full' required readOnly type='date' value={form.end_date} /></label>
        </div>
        <div className='grid gap-4 md:grid-cols-3'>
          {form.levels.map((level, index) => <fieldset key={level.level_number} className='rounded-xl border border-slate-800 p-4'>
            <legend className='px-2 font-semibold'>Level {level.level_number}</legend>
            <label><span className='field-label'>Intake Code</span><input className='w-full' required maxLength={50} value={level.intake_code} onChange={(event) => changeLevel(index, { intake_code: event.target.value })} /></label>
            <label className='mt-3 block'><span className='field-label'>Intake Name (optional)</span><input className='w-full' maxLength={100} value={level.intake_name} onChange={(event) => changeLevel(index, { intake_name: event.target.value })} /></label>
          </fieldset>)}
        </div>
        <div className='flex gap-2'><Button type='submit' loading={saving}>{editingId == null ? 'Create Batch' : 'Save changes'}</Button>{editingId != null && <Button type='button' variant='ghost' onClick={cancelEdit}>Cancel</Button>}</div>
      </form>
    </section>

    <section className='mt-7 table-wrap'>
      <table>
        <thead><tr><th>Batch</th><th>Program</th><th>Dates</th><th>Level Intake Codes</th><th><span className='sr-only'>Actions</span></th></tr></thead>
        <tbody>{batches.map((batch) => <tr key={batch.id}>
          <td>{batch.name}</td>
          <td>{programName(batch.program_id)}</td>
          <td>{batch.start_date} to {batch.end_date}</td>
          <td><div className='flex flex-wrap gap-2'>{batch.levels.map((level) => <span key={level.id} className='rounded-full bg-slate-800 px-2 py-1 text-xs'>L{level.level_number}: {level.intake_code}</span>)}</div></td>
          <td><div className='flex justify-end gap-2'><Button type='button' size='sm' variant='ghost' onClick={() => startEdit(batch)}>Edit</Button><Button type='button' size='sm' variant='danger' onClick={() => setDeleteId(batch.id)}>Delete</Button></div></td>
        </tr>)}</tbody>
      </table>
    </section>

    <ConfirmDialog open={deleteId != null} title='Delete this Batch?' description='Deletion is blocked when the Batch has Sections or Semesters.' confirmLabel='Delete' tone='danger' onClose={() => setDeleteId(null)} onConfirm={remove} />
  </div>;
}
