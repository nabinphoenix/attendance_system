import Link from "next/link";

const links = [
  ["Dashboard", "/admin/dashboard"],
  ["Programs", "/admin/academic/programs"],
  ["Batches", "/admin/academic/batches"],
  ["Sections", "/admin/academic/sections"],
  ["Subjects", "/admin/academic/subjects"],
  ["Teachers", "/admin/academic/teachers"],
  ["Students", "/admin/students"],
  ["Routine builder", "/admin/routine"],
  ["Intakes", "/admin/academic/intakes"],
  ["Rooms & blocks", "/admin/academic/rooms"],
  ["Modules", "/admin/academic/modules"],
  ["Module offerings", "/admin/academic/module-offerings"],
  ["Time slots", "/admin/academic/time-slots"],
  ["User access", "/admin/users"],
  ["Timetable", "/admin/timetable"],
  ["Imports", "/admin/imports"],
  ["Overrides", "/admin/overrides"],
];

export default function AdminNav() {
  return <aside className="w-full shrink-0 border-b border-slate-800 pb-4 md:w-52 md:border-b-0 md:border-r md:pr-4">
    <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Administration</p>
    <nav className="flex flex-wrap gap-2 md:flex-col">
      {links.map(([label, href]) => <Link key={href} href={href} className="rounded px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 hover:text-emerald-300">{label}</Link>)}
    </nav>
  </aside>;
}
