"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getRole, type Role } from "@/lib/auth";
export default function RoleShell({ role, children }: { role: string; children: React.ReactNode }) {
  const router=useRouter(); const [allowed,setAllowed]=useState(false);
  useEffect(()=>{let actual:Role|null=null;try{actual=getRole()}catch{}if(actual!==role){router.replace("/login")}else{setAllowed(true)}},[role,router]);
  if(!allowed)return <main className="grid min-h-screen place-items-center">Checking access…</main>;
  return <div className="min-h-screen"><header className="border-b border-slate-800 px-6 py-4"><Link href="/" className="font-bold text-emerald-400">AntimBench</Link><span className="ml-3 text-sm capitalize text-slate-400">{role} workspace</span></header><main className="p-6">{children}</main></div>;
}
