"use client";
import { cloneElement, ReactElement, ReactNode, useEffect, useId, useState } from "react";
import Brand from "@/components/Brand";

export function AuthMain({children,split=false}:{children:ReactNode;split?:boolean}){return <main className="grid min-h-screen place-items-center px-4 py-8 sm:px-6"><section className={`w-full min-w-0 border border-slate-800 bg-slate-900/85 shadow-2xl shadow-black/20 ${split?"max-w-5xl rounded-2xl lg:grid lg:grid-cols-[.9fr_1.1fr]":"max-w-lg rounded-2xl p-6 sm:p-8"}`}>{split&&<aside className="hidden border-r border-slate-800 bg-slate-950/70 p-10 lg:flex lg:flex-col lg:justify-between"><Brand/><div><p className="text-sm font-semibold uppercase tracking-[.16em] text-emerald-400">Attendance → intervention</p><h2 className="mt-4 text-3xl font-semibold leading-tight">Keep every class and every student in view.</h2><p className="mt-4 max-w-sm leading-7 text-slate-400">A focused workspace for college attendance, routines, and timely student support.</p></div><p className="text-xs text-slate-500">Secure access for students and college teams</p></aside>}<div className={split?"min-w-0 p-5 sm:p-10":""}>{split&&<div className="mb-8 lg:hidden"><Brand/></div>}{children}</div></section></main>}
export function Field({label,error,children,hint}:{label:string;error:string|false;children:ReactElement<{id?:string;disabled?:boolean;"aria-describedby"?:string}>;hint?:string}) {
  // Server-rendered inputs must not accept typing before React can retain it.
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const generatedId = useId();
  const id = children.props.id ?? generatedId;
  const messageId = `${id}-message`;
  const describedBy = [children.props["aria-describedby"], (error || hint) ? messageId : undefined].filter(Boolean).join(" ") || undefined;
  return <div className="min-w-0"><label htmlFor={id} className="field-label">{label}</label>{cloneElement(children, {id, disabled: !ready || children.props.disabled, "aria-describedby": describedBy})}{error?<p id={messageId} className="mt-1.5 text-sm text-red-400">{error}</p>:hint&&<p id={messageId} className="helper-text">{hint}</p>}</div>;
}
