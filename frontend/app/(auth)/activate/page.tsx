"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import api from "@/lib/api";
import { AuthMain, Field } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";
import { PasswordInput } from "@/components/ui/PasswordInput";

function ActivateAccount() {
  const token = useSearchParams().get("token") || "";
  const router = useRouter();
  const [info,setInfo] = useState<any>(null);
  const [password,setPassword] = useState("");
  const [error,setError] = useState("");
  const [done,setDone] = useState(false);
  const [loading,setLoading] = useState(false);
  useEffect(() => { if (!token) { setError("Invitation token is missing."); return; } api.get(`/api/v1/auth/activate/validate?token=${encodeURIComponent(token)}`).then((response) => setInfo(response.data)).catch(() => setError("This invitation is invalid or has expired.")); }, [token]);
  async function submit(event:FormEvent) { event.preventDefault(); setLoading(true); setError(""); try { await api.post("/api/v1/auth/activate",{token,password}); setDone(true); window.setTimeout(() => router.push("/student/dashboard"),700); } catch { setError("Your account could not be activated. Check the invitation and try again."); } finally { setLoading(false); } }
  return <AuthMain><form onSubmit={submit} className="space-y-5"><header><p className="text-sm font-semibold text-emerald-400">STUDENT INVITATION</p><h1 className="mt-2 text-3xl font-semibold">Activate your account</h1>{info && <p className="mt-2 text-slate-400">{info.student_name} · {info.email}</p>}</header>{error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200" role="alert">{error}</p>}{done ? <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200" role="status">Account activated. Signing you in…</p> : info && <><Field label="Choose a password" hint="Use at least 8 characters." error=""><PasswordInput required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} className="w-full" autoComplete="new-password" /></Field><Button className="w-full" size="lg" loading={loading}>{loading ? "Activating…" : "Activate account"}</Button></>}</form></AuthMain>;
}

export default function Page() { return <Suspense fallback={<main className="grid min-h-screen place-items-center text-sm text-slate-400">Loading invitation…</main>}><ActivateAccount /></Suspense>; }
