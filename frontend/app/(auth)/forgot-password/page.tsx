"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import api from "@/lib/api";
import { AuthMain, Field } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";
export default function ForgotPasswordPage() {
  const [email,setEmail]=useState(""); const [sent,setSent]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{await api.post("/api/v1/auth/forgot-password",{email:email.trim().toLowerCase()});setSent(true);}catch(error){setError(isAxiosError(error)&&error.response?.status===429?"Too many requests. Please wait before trying again.":"We could not request a reset. Please try again.");}finally{setBusy(false);}}
  return <AuthMain><form onSubmit={submit} className="space-y-5"><header><h1 className="text-[1.75rem] font-semibold">Forgot your password?</h1><p className="app-caption mt-2">Enter your registered email to receive a secure reset link.</p></header>
    {sent?<div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm leading-6">If an account exists for that email, password reset instructions have been sent. Check your inbox and spam folder. Resetting your password also unlocks your account.</div>:<><Field label="Email address" error={false}><input type="email" inputMode="email" autoComplete="email" autoCapitalize="none" required value={email} onChange={e=>setEmail(e.target.value)}/></Field><Button type="submit" className="w-full" loading={busy}>Send reset link</Button></>}
    {error&&<p role="alert" className="text-sm text-red-600 dark:text-red-300">{error}</p>}
    <Link href="/login" className="inline-flex min-h-11 items-center text-sm font-semibold text-emerald-600 underline dark:text-emerald-300">Back to sign in</Link>
  </form></AuthMain>;
}
