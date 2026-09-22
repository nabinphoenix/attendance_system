type Option = { value: string; label: string };

type ScheduleFilterBarProps = {
  days: readonly string[];
  day: string;
  onDayChange: (value: string) => void;
  classType: string;
  onClassTypeChange: (value: string) => void;
  classTypes: Option[];
  module?: string;
  onModuleChange?: (value: string) => void;
  modules?: Option[];
  teacher?: string;
  onTeacherChange?: (value: string) => void;
  teachers?: Option[];
  section?: string;
  onSectionChange?: (value: string) => void;
  date?: string;
  onDateChange?: (value: string) => void;
  minDate?: string;
  maxDate?: string;
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  onClear: () => void;
};

const selectClass = "!w-auto min-w-36 rounded-xl border-slate-200 bg-white px-3 py-2 text-sm font-semibold shadow-none dark:border-slate-700 dark:bg-slate-900";
const inputClass = "!w-auto min-w-44 rounded-xl border-slate-200 bg-white px-3 py-2 text-sm shadow-none dark:border-slate-700 dark:bg-slate-900";

function FilterSelect({ label, value, onChange, options, allLabel }: { label: string; value: string; onChange: (value: string) => void; options: Option[]; allLabel: string }) {
  return <label className="flex min-w-0 items-center gap-2 text-sm">
    <span className="shrink-0 font-semibold text-slate-500 dark:text-slate-400">{label}:</span>
    <select className={selectClass} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{allLabel}</option>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}

export function ScheduleFilterBar({ days, day, onDayChange, classType, onClassTypeChange, classTypes, module, onModuleChange, modules = [], teacher, onTeacherChange, teachers = [], section, onSectionChange, date, onDateChange, minDate, maxDate, search, onSearchChange, searchPlaceholder = "Search classes", onClear }: ScheduleFilterBarProps) {
  const hasFilters = Boolean(day || classType || module || teacher || section || date || search);
  return <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-4">
    <div className="flex flex-wrap items-center gap-3">
      <FilterSelect label="Day" value={day} onChange={onDayChange} options={days.map((label, value) => ({ value: String(value), label }))} allLabel="All days" />
      <FilterSelect label="Type" value={classType} onChange={onClassTypeChange} options={classTypes} allLabel="All types" />
      {module !== undefined && onModuleChange && <FilterSelect label="Module" value={module} onChange={onModuleChange} options={modules} allLabel="All modules" />}
      {teacher !== undefined && onTeacherChange && <FilterSelect label="Teacher" value={teacher} onChange={onTeacherChange} options={teachers} allLabel="All teachers" />}
      {section !== undefined && onSectionChange && <label className="flex min-w-0 items-center gap-2 text-sm"><span className="shrink-0 font-semibold text-slate-500 dark:text-slate-400">Section:</span><input className={inputClass} placeholder="Any section" value={section} onChange={(event) => onSectionChange(event.target.value)} /></label>}
      {date !== undefined && onDateChange && <label className="flex min-w-0 items-center gap-2 text-sm"><span className="shrink-0 font-semibold text-slate-500 dark:text-slate-400">Date:</span><input className="!w-auto rounded-xl border-slate-200 bg-white px-3 py-2 text-sm shadow-none dark:border-slate-700 dark:bg-slate-900" type="date" min={minDate} max={maxDate} value={date} onChange={(event) => onDateChange(event.target.value)} /></label>}
      {search !== undefined && onSearchChange && <label className="flex min-w-0 flex-1 items-center gap-2 text-sm"><span className="shrink-0 font-semibold text-slate-500 dark:text-slate-400">Search:</span><input className={`${inputClass} w-full`} placeholder={searchPlaceholder} value={search} onChange={(event) => onSearchChange(event.target.value)} /></label>}
      {hasFilters && <button type="button" className="ml-auto rounded-lg px-2 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-500/10 dark:text-emerald-300" onClick={onClear}>Clear filters</button>}
    </div>
  </div>;
}
