"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { type Role } from "@/lib/auth";
import Brand from "@/components/Brand";
import { Button } from "@/components/ui/Button";

type NavItem={label:string;href:string;icon:IconName};
type NavGroup={label:string;items:NavItem[]};
type IconName="dashboard"|"calendar"|"people"|"book"|"building"|"upload"|"shield"|"chart"|"qr"|"file"|"support";

const navigation:Record<Role,NavGroup[]>={
  admin:[
    {label:"Overview",items:[{label:"Dashboard",href:"/admin/dashboard",icon:"dashboard"}]},
    {label:"Attendance",items:[{label:"Routine",href:"/admin/routine",icon:"calendar"},{label:"Overrides",href:"/admin/overrides",icon:"calendar"}]},
    {label:"People",items:[{label:"Students",href:"/admin/students",icon:"people"},{label:"Teachers",href:"/admin/academic/teachers",icon:"people"},{label:"User access",href:"/admin/users",icon:"shield"}]},
    {label:"Academic",items:[{label:"Programs",href:"/admin/academic/programs",icon:"book"},{label:"Batches",href:"/admin/academic/batches",icon:"book"},{label:"Intakes",href:"/admin/academic/intakes",icon:"book"},{label:"Sections",href:"/admin/academic/sections",icon:"book"},{label:"Modules",href:"/admin/academic/modules",icon:"book"},{label:"Module offerings",href:"/admin/academic/module-offerings",icon:"book"},{label:"Rooms",href:"/admin/academic/rooms",icon:"building"},{label:"Time slots",href:"/admin/academic/time-slots",icon:"calendar"},{label:"Class types",href:"/admin/academic/class-types",icon:"book"}]},
    {label:"Operations",items:[{label:"Imports",href:"/admin/imports",icon:"upload"},{label:"Analytics",href:"/admin/analytics",icon:"chart"},{label:"Audit logs",href:"/admin/audit-log",icon:"file"}]},
  ],
  teacher:[{label:"Teaching",items:[{label:"Today & timetable",href:"/teacher/sessions",icon:"calendar"}]}],
  student:[{label:"My college",items:[{label:"Dashboard",href:"/student/dashboard",icon:"dashboard"},{label:"My routine",href:"/student/routine",icon:"calendar"},{label:"Check in",href:"/student/check-in",icon:"qr"},{label:"Attendance reports",href:"/student/reports",icon:"chart"}]}],
  coordinator:[{label:"Student support",items:[{label:"Cases",href:"/coordinator/cases",icon:"support"}]}],
  parent:[{label:"Family",items:[{label:"Notifications",href:"/parent/notifications",icon:"file"}]}],
};

const paths:Record<IconName,string>={
  dashboard:"M4 13h6V4H4v9Zm10 7h6V11h-6v9ZM4 20h6v-3H4v3Zm10-13h6V4h-6v3Z",
  calendar:"M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z",
  people:"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m7-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87m0-11.26a4 4 0 0 1 0 7.75",
  book:"M4 4h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H4V4Zm16 0h-4a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h4V4Z",
  building:"M3 21h18M6 21V7l6-4 6 4v14M9 10h.01M15 10h.01M9 14h.01M15 14h.01M10 21v-3h4v3",
  upload:"M12 16V4m0 0L7 9m5-5 5 5M4 15v5h16v-5",
  shield:"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-3-10 2 2 4-4",
  chart:"M4 20V10m6 10V4m6 16v-7m5 7H2",
  qr:"M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm12 0h2v2h-2v-2Zm4 0h2v7h-7v-2m0-3h2v2h-2v-2Zm4 1h2",
  file:"M6 2h8l4 4v16H6V2Zm8 0v5h5M9 13h6m-6 4h6",
  support:"M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-6v.01M9.1 9a3 3 0 1 1 4.2 2.75c-.8.4-1.3 1-1.3 1.75",
};

function Icon({name}:{name:IconName}){return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]}/></svg>}

export default function RoleShell({role,children}:{role:Role;children:React.ReactNode}){
  const router=useRouter();
  const pathname=usePathname();
  const[allowed,setAllowed]=useState(false);
  const[user,setUser]=useState<{name:string;email:string;role:string}|null>(null);
  const[mobileOpen,setMobileOpen]=useState(false);
  const[userMenuOpen,setUserMenuOpen]=useState(false);
  const[collapsed,setCollapsed]=useState(false);
  const groups=navigation[role];
  const flat=useMemo(()=>groups.flatMap(group=>group.items),[groups]);
  const current=flat.filter(item=>pathname===item.href||pathname.startsWith(`${item.href}/`)).sort((a,b)=>b.href.length-a.href.length)[0];

  useEffect(()=>{
    let active=true;
    api.get("/api/v1/auth/me").then(response=>{
      if(!active)return;
      if(response.data.role!==role){router.replace("/login");return}
      setUser(response.data);setAllowed(true);setCollapsed(localStorage.getItem("sidebar_collapsed")==="true");
    }).catch(()=>{if(active)router.replace("/login")});
    return()=>{active=false};
  },[role,router]);
  useEffect(()=>{setMobileOpen(false);setUserMenuOpen(false)},[pathname]);
  useEffect(()=>{if(!mobileOpen&&!userMenuOpen)return;const close=(event:KeyboardEvent)=>{if(event.key==="Escape"){setMobileOpen(false);setUserMenuOpen(false)}};window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close)},[mobileOpen,userMenuOpen]);

  function toggleCollapsed(){setCollapsed(value=>{localStorage.setItem("sidebar_collapsed",String(!value));return!value})}
  function logout(){void api.post("/api/v1/auth/logout").finally(()=>router.replace("/login"))}
  if(!allowed)return <main className="grid min-h-screen place-items-center px-4"><div role="status" className="text-center"><span className="mx-auto block h-8 w-8 animate-spin rounded-full border-2 border-emerald-400 border-r-transparent"/><p className="mt-3 text-sm text-slate-400">Checking access…</p></div></main>;

  const sidebar=<aside className={`flex h-full w-full flex-col border-r border-slate-800 bg-slate-950/95 transition-[width] ${collapsed?"lg:w-[4.75rem]":"lg:w-64"}`}>
    <div className="flex h-16 items-center justify-between border-b border-slate-800 px-4"><Brand compact={collapsed}/><button className="hidden rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white lg:block" onClick={toggleCollapsed} aria-label={collapsed?"Expand sidebar":"Collapse sidebar"}><svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 transition ${collapsed?"rotate-180":""}`} fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6"/></svg></button></div>
    <nav aria-label={`${role} navigation`} className="flex-1 space-y-5 overflow-y-auto px-3 py-5">{groups.map(group=><div key={group.label}>{!collapsed&&<p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[.14em] text-slate-500">{group.label}</p>}<div className="space-y-1">{group.items.map(item=>{const active=pathname===item.href||pathname.startsWith(`${item.href}/`);return <Link title={collapsed?item.label:undefined} aria-current={active?"page":undefined} key={item.href} href={item.href} className={`relative flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition ${active?"bg-emerald-500/12 text-emerald-300":"text-slate-400 hover:bg-slate-800/80 hover:text-slate-100"} ${collapsed?"justify-center":""}`}>{active&&<span className="absolute inset-y-2 left-0 w-0.5 rounded-r bg-emerald-400"/>}<Icon name={item.icon}/>{!collapsed&&<span>{item.label}</span>}</Link>})}</div></div>)}</nav>
    <div className="border-t border-slate-800 p-3"><button onClick={logout} title={collapsed?"Log out":undefined} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-red-500/10 hover:text-red-300 ${collapsed?"justify-center":""}`}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M10 17l5-5-5-5m5 5H3m11-9h6v18h-6"/></svg>{!collapsed&&"Log out"}</button></div>
  </aside>;

  return <div className="min-h-screen bg-slate-950">
    <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{sidebar}</div>
    {mobileOpen&&<div className="fixed inset-0 z-50 lg:hidden"><button aria-label="Close navigation" className="absolute inset-0 bg-black/65" onClick={()=>setMobileOpen(false)}/><div className="relative h-full w-[min(19rem,86vw)]">{sidebar}</div></div>}
    <div className={`min-h-screen transition-[padding] ${collapsed?"lg:pl-[4.75rem]":"lg:pl-64"}`}>
      <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-4 backdrop-blur sm:px-6 lg:px-8"><Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" onClick={()=>setMobileOpen(true)}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg></Button><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-100">{current?.label??`${role[0].toUpperCase()}${role.slice(1)} workspace`}</p><p className="hidden text-xs capitalize text-slate-500 sm:block">{role} workspace</p></div><div className="relative flex items-center gap-3"><div className="hidden text-right sm:block"><p className="max-w-48 truncate text-sm font-medium text-slate-200">{user?.name??"Signed-in user"}</p><p className="text-xs capitalize text-slate-500">{role}</p></div><button aria-label="Open user menu" aria-expanded={userMenuOpen} onClick={()=>setUserMenuOpen(value=>!value)} className="grid h-9 w-9 place-items-center rounded-full border border-slate-700 bg-slate-800 text-sm font-semibold text-emerald-300 transition hover:border-slate-500 hover:bg-slate-700">{(user?.name??role).charAt(0).toUpperCase()}</button>{userMenuOpen&&<div className="panel absolute right-0 top-12 w-64 p-2"><div className="border-b border-slate-800 px-3 py-2"><p className="truncate text-sm font-semibold text-slate-100">{user?.name??"Signed-in user"}</p><p className="mt-0.5 truncate text-xs text-slate-400">{user?.email}</p><p className="mt-1 text-xs capitalize text-emerald-300">{role}</p></div><button onClick={logout} className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-red-300 hover:bg-red-500/10">Log out</button></div>}</div></header>
      <main className="page-container min-w-0">{children}</main>
    </div>
  </div>;
}
