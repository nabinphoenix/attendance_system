"use client";
import { ReactNode } from "react";
export type College = { id: number; name: string; slug: string; contact_email: string | null; address: string | null; is_active: boolean };
export function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg ?? "Invalid value").join(". ");
  return "The request could not be completed. Please try again.";
}
export function Heading({title, children}: {title: string; children: ReactNode}) { return <header className="mb-6"><p className="text-xs font-semibold uppercase tracking-widest text-emerald-600">Super Admin</p><h1 className="mt-2 text-3xl font-semibold">{title}</h1><p className="app-caption mt-2 max-w-3xl text-sm leading-6">{children}</p></header>; }
export function Notice({error, success}: {error?: string; success?: string}) { return error ? <p role="alert" className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">{error}</p> : success ? <p role="status" className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">{success}</p> : null; }
export function Field({label, children}: {label:string; children:ReactNode}) { return <label className="block space-y-2 text-sm"><span className="font-medium">{label}</span>{children}</label>; }
export function Pager({page,total,onChange}: {page:number;total:number;onChange:(page:number)=>void}) { return <div className="mt-4 flex items-center justify-between text-sm"><span className="app-caption">{total} records ? Page {page} of {Math.max(1,Math.ceil(total/25))}</span><div className="flex gap-3"><button disabled={page<=1} onClick={()=>onChange(page-1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">Previous</button><button disabled={page*25>=total} onClick={()=>onChange(page+1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">Next</button></div></div>; }
export const inputClass = "w-full rounded-lg border px-3 py-2.5";
