"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { Heading, Notice, errorMessage } from "@/components/PlatformUI";
export default function Overview() {
  const [data,setData]=useState<Record<string,number>|null>(null); const [error,setError]=useState("");
  useEffect(()=>{api.get("/api/v1/platform/overview").then(r=>setData(r.data)).catch(e=>setError(errorMessage(e)));},[]);
  return <><Heading title="Platform overview">Manage your colleges and follow activity across the entire platform.</Heading><Notice error={error}/>{!data&&!error?<p role="status">Loading platform overview?</p>:data&&<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Object.entries(data).map(([key,value])=><div className="panel p-6" key={key}><p className="app-caption text-sm capitalize">{key.replaceAll("_"," ")}</p><p className="mt-3 text-4xl font-semibold">{value.toLocaleString()}</p></div>)}</div>}<div className="mt-6 grid gap-4 md:grid-cols-2"><Link href="/super-admin/colleges" className="panel block p-6 transition hover:border-emerald-500"><h2 className="text-lg font-semibold">Manage colleges ?</h2><p className="app-caption mt-2 text-sm">Create a college or open its academic and attendance workspace.</p></Link><Link href="/super-admin/audit-log" className="panel block p-6 transition hover:border-emerald-500"><h2 className="text-lg font-semibold">Review system activity ?</h2><p className="app-caption mt-2 text-sm">See who changed records, in which college, and when.</p></Link></div></>;
}
