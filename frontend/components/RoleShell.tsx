"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { type Role } from "@/lib/auth";
import Brand from "@/components/Brand";
import ProfileAvatar from "@/components/ProfileAvatar";
import { trapDialogFocus } from "@/components/ui/dialogFocus";
import ThemeToggle from "@/components/ThemeToggle";

type NavItem = { label: string; href: string; icon: IconName };
type NavGroup = { label: string; items: NavItem[] };
type IconName = "dashboard" | "calendar" | "people" | "book" | "building" | "upload" | "shield" | "chart" | "qr" | "file" | "support" | "settings";
type CurrentUser = { name: string; email: string; role: string; avatar_url?: string | null; college_name?: string | null; active_college_id?: number | null };

const navigation: Record<Role, NavGroup[]> = {
  super_admin: [
    { label: "Platform", items: [{ label: "Overview", href: "/super-admin/dashboard", icon: "dashboard" }, { label: "Colleges", href: "/super-admin/colleges", icon: "building" }, { label: "Accounts", href: "/super-admin/users", icon: "people" }] },
    { label: "Governance", items: [{ label: "System audit log", href: "/super-admin/audit-log", icon: "shield" }, { label: "Configuration", href: "/super-admin/configuration", icon: "settings" }] },
  ],
  admin: [
    { label: 'Progression', items: [{ label: 'Promotions', href: '/admin/academic/promotions', icon: 'calendar' }] },
    { label: "Overview", items: [{ label: "Dashboard", href: "/admin/dashboard", icon: "dashboard" }, { label: "AI assistant", href: "/admin/assistant", icon: "support" }] },
    { label: "Attendance", items: [{ label: "Routine", href: "/admin/routine", icon: "calendar" }, { label: "Room availability", href: "/admin/room-availability", icon: "building" }, { label: "Overrides", href: "/admin/overrides", icon: "calendar" }, { label: "Campus networks", href: "/admin/campus-networks", icon: "shield" }] },
    { label: "People", items: [{ label: "Students", href: "/admin/students", icon: "people" }, { label: "Teachers", href: "/admin/academic/teachers", icon: "people" }, { label: "User access", href: "/admin/users", icon: "shield" }] },
    { label: "Academic", items: [{ label: "Semester resources", href: "/admin/academic/semester-resources", icon: "file" }, { label: "Programs", href: "/admin/academic/programs", icon: "book" }, { label: "Batches", href: "/admin/academic/batches", icon: "book" }, { label: "Intakes", href: "/admin/academic/intakes", icon: "book" }, { label: "Sections", href: "/admin/academic/sections", icon: "book" }, { label: "Courses", href: "/admin/academic/modules", icon: "book" }, { label: "Course Assignments", href: "/admin/academic/module-offerings", icon: "book" }, { label: "Rooms", href: "/admin/academic/rooms", icon: "building" }, { label: "Time slots", href: "/admin/academic/time-slots", icon: "calendar" }, { label: "Class types", href: "/admin/academic/class-types", icon: "book" }] },
    { label: "Operations", items: [{ label: "Google Workspace", href: "/admin/google-workspace", icon: "file" }, { label: "Imports", href: "/admin/imports", icon: "upload" }, { label: "Analytics", href: "/admin/analytics", icon: "chart" }, { label: "Audit logs", href: "/admin/audit-log", icon: "file" }] },
  ],
  teacher: [{ label: "Teaching", items: [{ label: "Academic calendars", href: "/teacher/academic-calendars", icon: "file" }, { label: "Today & timetable", href: "/teacher/sessions", icon: "calendar" }, { label: "Room availability", href: "/teacher/room-availability", icon: "building" }, { label: "Manual attendance", href: "/teacher/attendance", icon: "people" }, { label: "Attendance analysis", href: "/teacher/analysis", icon: "chart" }] }],
  student: [{ label: "My college", items: [{ label: "Semester resources", href: "/student/semester-resources", icon: "file" }, { label: "Dashboard", href: "/student/dashboard", icon: "dashboard" }, { label: "My routine", href: "/student/routine", icon: "calendar" }, { label: "Room availability", href: "/student/room-availability", icon: "building" }, { label: "Check in", href: "/student/check-in", icon: "qr" }, { label: "Attendance reports", href: "/student/reports", icon: "chart" }] }],
  coordinator: [{ label: "Student support", items: [{ label: "Cases", href: "/coordinator/cases", icon: "support" }] }],
  parent: [{ label: "Family", items: [{ label: "Notifications", href: "/parent/notifications", icon: "file" }] }],
};

const paths: Record<IconName, string> = {
  dashboard: "M4 13h6V4H4v9Zm10 7h6V11h-6v9ZM4 20h6v-3H4v3Zm10-13h6V4h-6v3Z",
  calendar: "M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z",
  people: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m7-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87m0-11.26a4 4 0 0 1 0 7.75",
  book: "M4 4h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H4V4Zm16 0h-4a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h4V4Z",
  building: "M3 21h18M6 21V7l6-4 6 4v14M9 10h.01M15 10h.01M9 14h.01M15 14h.01M10 21v-3h4v3",
  upload: "M12 16V4m0 0L7 9m5-5 5 5M4 15v5h16v-5",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-3-10 2 2 4-4",
  chart: "M4 20V10m6 10V4m6 16v-7m5 7H2",
  qr: "M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm12 0h2v2h-2v-2Zm4 0h2v7h-7v-2m0-3h2v2h-2v-2Zm4 1h2",
  file: "M6 2h8l4 4v16H6V2Zm8 0v5h5M9 13h6m-6 4h6",
  support: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-6v.01M9.1 9a3 3 0 1 1 4.2 2.75c-.8.4-1.3 1-1.3 1.75",
  settings: "M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5ZM19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.08h-3v-.08A1.7 1.7 0 0 0 10.68 18.7a1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7.02 15a1.7 1.7 0 0 0-1.56-1.03h-.08v-3h.08A1.7 1.7 0 0 0 7.02 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06L8.74 5.88l.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.08h3v.08a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 8l-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.08v3h-.08A1.7 1.7 0 0 0 19.4 15Z",
};

function Icon({ name }: { name: IconName }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}

export default function RoleShell({ role, children }: { role: Role; children: React.ReactNode }) {
  const pathname = usePathname();
  const mobileDialog = useRef<HTMLDialogElement>(null);
  const mobileTrigger = useRef<HTMLButtonElement>(null);
  const [allowed, setAllowed] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const groups = useMemo(() => [...navigation[role], { label: "Account", items: [{ label: "Settings", href: "/settings", icon: "settings" as IconName }] }], [role]);
  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const current = flat.filter((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)).sort((a, b) => b.href.length - a.href.length)[0];

  useEffect(() => {
    let active = true;
    const confirmAccess = () => api.get<CurrentUser>("/api/v1/auth/me").then((response) => {
      if (!active) return;
      if (response.data.role !== role && !(role === "admin" && response.data.role === "super_admin" && response.data.active_college_id)) { window.location.replace("/login"); return; }
      setUser(response.data);
      setAllowed(true);
      setCollapsed(localStorage.getItem("sidebar_collapsed") === "true");
    }).catch(() => { if (active) { setAllowed(false); window.location.replace("/login"); } });
    void confirmAccess();
    const recheckOnRestore = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      setAllowed(false);
      void confirmAccess();
    };
    window.addEventListener("pageshow", recheckOnRestore);
    return () => { active = false; window.removeEventListener("pageshow", recheckOnRestore); };
  }, [role]);

  useEffect(() => { setMobileOpen(false); setUserMenuOpen(false); }, [pathname]);
  useEffect(() => {
    const dialog = mobileDialog.current;
    if (!mobileOpen) { dialog?.close(); return; }
    dialog?.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [mobileOpen]);
  useEffect(() => {
    if (!mobileOpen && !userMenuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { setMobileOpen(false); setUserMenuOpen(false); } };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [mobileOpen, userMenuOpen]);
  useEffect(() => {
    const refreshProfile = (event: Event) => setUser((current) => current ? { ...current, ...(event as CustomEvent<Partial<CurrentUser>>).detail } : current);
    window.addEventListener("antimbench-profile-updated", refreshProfile);
    return () => window.removeEventListener("antimbench-profile-updated", refreshProfile);
  }, []);

  function toggleCollapsed() {
    setCollapsed((value) => { localStorage.setItem("sidebar_collapsed", String(!value)); return !value; });
  }
  async function logout(destination = "/login") {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutError("");
    try {
      await api.post("/api/v1/auth/logout");
      sessionStorage.removeItem("platform_college_id");
      window.location.replace(destination);
    } catch {
      setLogoutError("We couldn't sign you out. Please try again.");
      setLoggingOut(false);
    }
  }

  function logoutToHome(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    void logout("/");
  }

  if (!allowed) return <main className="grid min-h-screen place-items-center px-4"><div role="status" className="text-center"><span className="mx-auto block h-9 w-9 animate-spin rounded-full border-2 border-emerald-400 border-r-transparent" /><p className="mt-3 text-sm app-caption">Opening your workspace…</p></div></main>;

  const sidebar = (mobile = false) => { const isCompact = collapsed && !mobile; return <aside className={`app-sidebar flex h-full w-full flex-col border-r transition-[width] ${isCompact ? "lg:w-[4.75rem]" : "lg:w-64"}`}>
    <div className="app-divider flex h-[4.5rem] items-center justify-between border-b px-4"><Brand compact={isCompact} onClick={logoutToHome} />{mobile && <button type="button" aria-label="Close navigation" className="h-11 w-11 shrink-0 rounded-lg text-xl" onClick={() => setMobileOpen(false)}><span aria-hidden="true">&#215;</span></button>}<button className="hidden rounded-lg p-2 app-caption hover:bg-emerald-500/10 hover:text-emerald-600 lg:block" onClick={toggleCollapsed} aria-label={isCompact ? "Expand sidebar" : "Collapse sidebar"}><svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 transition ${isCompact ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg></button></div>
    <nav aria-label={`${role} navigation`} className="flex-1 space-y-5 overflow-y-auto px-3 py-5">{mobile && user?.role === "super_admin" && role === "admin" && <Link href="/super-admin/colleges" onClick={() => setMobileOpen(false)} className="app-nav-link flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium"><Icon name="building" />Back to platform</Link>}{groups.map((group) => <div key={group.label}>{!isCompact && <p className="app-nav-label mb-2 px-3 text-[11px] font-semibold uppercase tracking-[.14em]">{group.label}</p>}<div className="space-y-1">{group.items.map((item) => { const active = pathname === item.href || pathname.startsWith(`${item.href}/`); return <Link title={isCompact ? item.label : undefined} aria-current={active ? "page" : undefined} key={item.href} href={item.href} onClick={() => setMobileOpen(false)} className={`app-nav-link relative flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition ${active ? "app-nav-link-active" : ""} ${isCompact ? "justify-center" : ""}`}>{active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-r bg-emerald-500" />}<Icon name={item.icon} />{!isCompact && <span>{item.label}</span>}</Link>; })}</div></div>)}</nav>
    <div className="app-divider border-t p-3"><button onClick={() => void logout()} disabled={loggingOut} title={isCompact ? "Log out" : undefined} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-red-500 transition hover:bg-red-500/10 disabled:cursor-wait disabled:opacity-60 ${isCompact ? "justify-center" : ""}`}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M10 17l5-5-5-5m5 5H3m11-9h6v18h-6" /></svg>{!isCompact && (loggingOut ? "Logging out…" : "Log out")}</button>{logoutError && !isCompact && <p className="mt-2 px-2 text-xs text-red-400" role="alert">{logoutError}</p>}</div>
  </aside>; };

  return <div className="app-shell">
    <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{sidebar()}</div>
    <dialog onKeyDown={trapDialogFocus} ref={mobileDialog} aria-label="Mobile navigation" onClose={() => { setMobileOpen(false); mobileTrigger.current?.focus(); }} onCancel={() => setMobileOpen(false)} className="fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-[min(19rem,86vw)] max-w-full border-0 p-0" onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX > rect.right || event.clientX < rect.left) setMobileOpen(false); } }}>{sidebar(true)}</dialog>
    <div className={`min-h-screen w-full min-w-0 max-w-full transition-[padding] ${collapsed ? "lg:pl-[4.75rem]" : "lg:pl-64"}`}>
      <header className="app-header sticky top-0 z-30 flex h-[4.5rem] items-center gap-2 border-b px-4 sm:gap-3 backdrop-blur sm:px-6 lg:px-8">
        <button ref={mobileTrigger} className="grid h-11 w-11 shrink-0 place-items-center rounded-lg app-caption hover:bg-emerald-500/10 hover:text-emerald-600 lg:hidden" aria-label="Open navigation" aria-expanded={mobileOpen} onClick={(event) => { event.currentTarget.focus(); setMobileOpen(true); }}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
        <div className="min-w-0 flex-1"><p className="app-title truncate text-sm font-semibold">{current?.label ?? `${role[0].toUpperCase()}${role.slice(1)} workspace`}</p><p className="app-caption hidden text-xs capitalize sm:block">{user?.college_name ? `${user.college_name} / ${role.replace("_", " ")}` : `${role.replace("_", " ")} workspace`}</p></div>
        {user?.role === "super_admin" && role === "admin" && <Link href="/super-admin/colleges" className="hidden rounded-lg border px-3 py-2 text-xs font-semibold sm:block">Back to platform</Link>}
        <ThemeToggle compact />
        <div className="relative"><button aria-label="Open account menu" aria-expanded={userMenuOpen} onClick={() => setUserMenuOpen((value) => !value)} className="rounded-full transition hover:scale-[1.03]"><ProfileAvatar name={user?.name ?? role} src={user?.avatar_url} /></button>{userMenuOpen && <div className="app-user-menu absolute right-0 top-12 w-[min(18rem,calc(100vw-2rem))] overflow-hidden rounded-xl border p-2 shadow-xl"><div className="app-divider flex items-center gap-3 border-b px-2 py-3"><ProfileAvatar name={user?.name ?? role} src={user?.avatar_url} /><div className="min-w-0"><p className="app-user-name truncate text-sm font-semibold">{user?.name ?? "Signed-in user"}</p><p className="app-caption mt-0.5 truncate text-xs">{user?.email}</p><p className="mt-1 text-xs capitalize text-emerald-600">{role}</p></div></div><Link href="/settings" className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold app-caption hover:bg-emerald-500/10 hover:text-emerald-700"><Icon name="settings" />Account settings</Link><button onClick={() => void logout()} disabled={loggingOut} className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-red-500 hover:bg-red-500/10 disabled:cursor-wait disabled:opacity-60">{loggingOut ? "Logging out…" : "Log out"}</button>{logoutError && <p className="px-3 py-2 text-xs text-red-400" role="alert">{logoutError}</p>}</div>}</div>
      </header>
      <main className="page-container min-w-0">{children}</main>
    </div>
  </div>;
}
