import Link from "next/link";

const links = [
  ["Semester resources", "/admin/academic/semester-resources"],
  ["AI assistant", "/admin/assistant"],
  ["Promotions", "/admin/academic/promotions"],
  ["Dashboard", "/admin/dashboard"],
  ["Programs", "/admin/academic/programs"],
  ["Batches", "/admin/academic/batches"],
  ["Levels & Intake Codes", "/admin/academic/intakes"],
  ["Semesters", "/admin/academic/semester-resources"],
  ["Sections", "/admin/academic/sections"],
  ["Courses", "/admin/academic/modules"],
  ["Course Assignments", "/admin/academic/module-offerings"],
  ["Teachers", "/admin/academic/teachers"],
  ["Students", "/admin/students"],
  ["Routines", "/admin/routine"],
  ["Rooms & blocks", "/admin/academic/rooms"],
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