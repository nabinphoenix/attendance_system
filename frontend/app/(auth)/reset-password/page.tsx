"use client";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import api from "@/lib/api";
import { AuthMain, Field } from "@/components/auth/AuthCard";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Button } from "@/components/ui/Button";
export default function ResetPasswordPage(){
  const token=useRef(""); const started=useRef(false); const [status,setStatus]=useState<"checking"|"ready"|"invalid"|"done">("checking");
  const [password,setPassword]=useState(""); const [confirmation,setConfirmation]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  useEffect(()=>{if(started.current)return;started.current=true;token.current=new URLSearchParams(window.location.hash.slice(1)).get("token")||"";window.history.replaceState(null,"",window.location.pathname);if(!token.current){setStatus("invalid");return;}api.post("/api/v1/auth/reset-password/validate",{token:token.current}).then(()=>setStatus("ready")).catch(()=>setStatus("invalid"));},[]);
  async function submit(event:FormEvent){event.preventDefault();setError("");if(password!==confirmation){setError("The two passwords do not match.");return;}setBusy(true);try{await api.post("/api/v1/auth/reset-password",{token:token.current,new_password:password,confirm_password:confirmation});token.current="";setPassword("");setConfirmation("");setStatus("done");}catch(error){const response=isAxiosError(error)?error.response:undefined;if(response?.status===400){setStatus("invalid");}else if(response?.status===429){setError("Too many requests. Please wait before trying again.");}else if(response?.status===422){setError("Choose a stronger password with at least 8 characters. Avoid common passwords; shorten it if it is very long.");}else{setError("Unable to reset your password. Please try again.");}}finally{setBusy(false);}}
  return <AuthMain><div className="space-y-5"><header><h1 className="text-[1.75rem] font-semibold">Reset your password</h1><p className="app-caption mt-2">Choose a strong password you do not use elsewhere.</p></header>
    {status==="checking"&&<p role="status">Verifying your reset link...</p>}
    {status==="invalid"&&<div role="alert"><p>This reset link is invalid or expired. Request a new link to continue.</p><Link href="/forgot-password" className="mt-3 inline-flex min-h-11 items-center font-semibold text-emerald-600 underline dark:text-emerald-300">Request another reset link</Link></div>}
    {status==="done"&&<p role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">Your password has been reset and your account unlocked. Please sign in again.</p>}
    {status==="ready"&&<form onSubmit={submit} className="space-y-5"><Field label="New password" error={false} hint="At least 8 characters. Avoid common passwords."><PasswordInput required minLength={8} maxLength={72} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></Field><Field label="Confirm new password" error={false}><PasswordInput required minLength={8} maxLength={72} autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></Field>{error&&<p role="alert" className="text-sm text-red-600 dark:text-red-300">{error}</p>}<Button type="submit" className="w-full" loading={busy}>Reset password</Button></form>}
    <Link href="/login" className="inline-flex min-h-11 items-center text-sm font-semibold text-emerald-600 underline dark:text-emerald-300">Back to sign in</Link>
  </div></AuthMain>;
}
