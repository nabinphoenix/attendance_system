"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { type Role } from "@/lib/auth";
import Brand from "@/components/Brand";
import ProfileAvatar from "@/components/ProfileAvatar";
import ThemeToggle from "@/components/ThemeToggle";

type NavItem = { label: string; href: string; icon: IconName };
type NavGroup = { label: string; items: NavItem[] };
type IconName = "dashboard" | "calendar" | "people" | "book" | "building" | "upload" | "shield" | "chart" | "qr" | "file" | "support" | "settings";
type CurrentUser = { name: string; email: string; role: string; avatar_url?: string | null };

const navigation: Record<Role, NavGroup[]> = {
  admin: [
    { label: "Overview", items: [{ label: "Dashboard", href: "/admin/dashboard", icon: "dashboard" }] },
    { label: "Attendance", items: [{ label: "Routine", href: "/admin/routine", icon: "calendar" }, { label: "Overrides", href: "/admin/overrides", icon: "calendar" }] },
    { label: "People", items: [{ label: "Students", href: "/admin/students", icon: "people" }, { label: "Teachers", href: "/admin/academic/teachers", icon: "people" }, { label: "User access", href: "/admin/users", icon: "shield" }] },
    { label: "Academic", items: [{ label: "Programs", href: "/admin/academic/programs", icon: "book" }, { label: "Batches", href: "/admin/academic/batches", icon: "book" }, { label: "Intakes", href: "/admin/academic/intakes", icon: "book" }, { label: "Sections", href: "/admin/academic/sections", icon: "book" }, { label: "Modules", href: "/admin/academic/modules", icon: "book" }, { label: "Module offerings", href: "/admin/academic/module-offerings", icon: "book" }, { label: "Rooms", href: "/admin/academic/rooms", icon: "building" }, { label: "Time slots", href: "/admin/academic/time-slots", icon: "calendar" }, { label: "Class types", href: "/admin/academic/class-types", icon: "book" }] },
    { label: "Operations", items: [{ label: "Imports", href: "/admin/imports", icon: "upload" }, { label: "Analytics", href: "/admin/analytics", icon: "chart" }, { label: "Audit logs", href: "/admin/audit-log", icon: "file" }] },
  ],
  teacher: [{ label: "Teaching", items: [{ label: "Today & timetable", href: "/teacher/sessions", icon: "calendar" }] }],
  student: [{ label: "My college", items: [{ label: "Dashboard", href: "/student/dashboard", icon: "dashboard" }, { label: "My routine", href: "/student/routine", icon: "calendar" }, { label: "Check in", href: "/student/check-in", icon: "qr" }, { label: "Attendance reports", href: "/student/reports", icon: "chart" }] }],
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
  const router = useRouter();
  const pathname = usePathname();
  const [allowed, setAllowed] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const groups = useMemo(() => [...navigation[role], { label: "Account", items: [{ label: "Settings", href: "/settings", icon: "settings" as IconName }] }], [role]);
  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const current = flat.filter((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)).sort((a, b) => b.href.length - a.href.length)[0];

  useEffect(() => {
    let active = true;
    api.get<CurrentUser>("/api/v1/auth/me").then((response) => {
      if (!active) return;
      if (response.data.role !== role) { router.replace("/login"); return; }
      setUser(response.data);
      setAllowed(true);
      setCollapsed(localStorage.getItem("sidebar_collapsed") === "true");
    }).catch(() => { if (active) router.replace("/login"); });
    return () => { active = false; };
  }, [role, router]);

  useEffect(() => { setMobileOpen(false); setUserMenuOpen(false); }, [pathname]);
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
  function logout() { void api.post("/api/v1/auth/logout").finally(() => router.replace("/login")); }

  if (!allowed) return <main className="grid min-h-screen place-items-center px-4"><div role="status" className="text-center"><span className="mx-auto block h-9 w-9 animate-spin rounded-full border-2 border-emerald-400 border-r-transparent" /><p className="mt-3 text-sm app-caption">Opening your workspace…</p></div></main>;

  const sidebar = <aside className={`app-sidebar flex h-full w-full flex-col border-r transition-[width] ${collapsed ? "lg:w-[4.75rem]" : "lg:w-64"}`}>
    <div className="app-divider flex h-[4.5rem] items-center justify-between border-b px-4"><Brand compact={collapsed} /><button className="hidden rounded-lg p-2 app-caption hover:bg-emerald-500/10 hover:text-emerald-600 lg:block" onClick={toggleCollapsed} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}><svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 transition ${collapsed ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg></button></div>
    <nav aria-label={`${role} navigation`} className="flex-1 space-y-5 overflow-y-auto px-3 py-5">{groups.map((group) => <div key={group.label}>{!collapsed && <p className="app-nav-label mb-2 px-3 text-[11px] font-semibold uppercase tracking-[.14em]">{group.label}</p>}<div className="space-y-1">{group.items.map((item) => { const active = pathname === item.href || pathname.startsWith(`${item.href}/`); return <Link title={collapsed ? item.label : undefined} aria-current={active ? "page" : undefined} key={item.href} href={item.href} className={`app-nav-link relative flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition ${active ? "app-nav-link-active" : ""} ${collapsed ? "justify-center" : ""}`}>{active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-r bg-emerald-500" />}<Icon name={item.icon} />{!collapsed && <span>{item.label}</span>}</Link>; })}</div></div>)}</nav>
    <div className="app-divider border-t p-3"><button onClick={logout} title={collapsed ? "Log out" : undefined} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-red-500 transition hover:bg-red-500/10 ${collapsed ? "justify-center" : ""}`}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M10 17l5-5-5-5m5 5H3m11-9h6v18h-6" /></svg>{!collapsed && "Log out"}</button></div>
  </aside>;

  return <div className="app-shell">
    <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{sidebar}</div>
    {mobileOpen && <div className="fixed inset-0 z-50 lg:hidden"><button aria-label="Close navigation" className="absolute inset-0 bg-black/45" onClick={() => setMobileOpen(false)} /><div className="relative h-full w-[min(19rem,86vw)]">{sidebar}</div></div>}
    <div className={`min-h-screen transition-[padding] ${collapsed ? "lg:pl-[4.75rem]" : "lg:pl-64"}`}>
      <header className="app-header sticky top-0 z-30 flex h-[4.5rem] items-center gap-3 border-b px-4 backdrop-blur sm:px-6 lg:px-8">
        <button className="grid h-10 w-10 place-items-center rounded-lg app-caption hover:bg-emerald-500/10 hover:text-emerald-600 lg:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
        <div className="min-w-0 flex-1"><p className="app-title truncate text-sm font-semibold">{current?.label ?? `${role[0].toUpperCase()}${role.slice(1)} workspace`}</p><p className="app-caption hidden text-xs capitalize sm:block">{role} workspace</p></div>
        <ThemeToggle compact />
        <div className="relative"><button aria-label="Open account menu" aria-expanded={userMenuOpen} onClick={() => setUserMenuOpen((value) => !value)} className="rounded-full transition hover:scale-[1.03]"><ProfileAvatar name={user?.name ?? role} src={user?.avatar_url} /></button>{userMenuOpen && <div className="app-user-menu absolute right-0 top-12 w-72 overflow-hidden rounded-xl border p-2 shadow-xl"><div className="app-divider flex items-center gap-3 border-b px-2 py-3"><ProfileAvatar name={user?.name ?? role} src={user?.avatar_url} /><div className="min-w-0"><p className="app-user-name truncate text-sm font-semibold">{user?.name ?? "Signed-in user"}</p><p className="app-caption mt-0.5 truncate text-xs">{user?.email}</p><p className="mt-1 text-xs capitalize text-emerald-600">{role}</p></div></div><Link href="/settings" className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold app-caption hover:bg-emerald-500/10 hover:text-emerald-700"><Icon name="settings" />Account settings</Link><button onClick={logout} className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-red-500 hover:bg-red-500/10">Log out</button></div>}</div>
      </header>
      <main className="page-container min-w-0">{children}</main>
    </div>
  </div>;
}
