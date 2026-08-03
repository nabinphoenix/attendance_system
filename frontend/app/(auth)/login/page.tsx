"use client";
import Link from "next/link";
import {FormEvent,useState} from "react";
import {useRouter} from "next/navigation";
import {jwtDecode} from "jwt-decode";
import api from "@/lib/api";
import {storeToken,type Role} from "@/lib/auth";
import {PasswordInput} from "@/components/ui/PasswordInput";
import {AuthMain,Field} from "@/components/auth/AuthCard";

const input="w-full rounded-xl border bg-slate-900 px-3 py-3 outline-none transition focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400";
export default function LoginPage(){
  const router=useRouter();const[email,setEmail]=useState("");const[password,setPassword]=useState("");const[touched,setTouched]=useState(false);const[error,setError]=useState("");const[loading,setLoading]=useState(false);
  const emailError=touched&&(!email.trim()?"Email is required":!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)?"Enter a valid email address":"");const passwordError=touched&&!password?"Password is required":"";const invalid=!!emailError||!!passwordError;
  async function submit(e:FormEvent){e.preventDefault();setTouched(true);setError("");if(!email||!password||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))return;setLoading(true);try{const{data}=await api.post("/api/v1/auth/login",{email:email.trim(),password});storeToken(data.access_token);const role=jwtDecode<{role:Role}>(data.access_token).role;router.push(role==="teacher"?"/teacher/sessions":role==="student"?"/student/dashboard":`/${role}/dashboard`)}catch{setError("Invalid email or password")}finally{setLoading(false)}}
  return <AuthMain><form noValidate onSubmit={submit} className="space-y-5"><header><p className="text-sm font-semibold text-emerald-400">ANTIMBENCH</p><h1 className="mt-2 text-3xl font-bold">Welcome back</h1><p className="mt-2 text-slate-400">Log in to your college workspace.</p></header>{error&&<p role="alert" className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">{error}</p>}<Field label="Email" error={emailError}><input value={email} onChange={e=>setEmail(e.target.value)} onBlur={()=>setTouched(true)} className={`${input} ${emailError?"border-red-500":"border-slate-700"}`} type="email" autoComplete="email"/></Field><Field label="Password" error={passwordError}><PasswordInput value={password} onChange={e=>setPassword(e.target.value)} onBlur={()=>setTouched(true)} className={`${input} ${passwordError?"border-red-500":"border-slate-700"}`} autoComplete="current-password"/></Field><button disabled={loading||invalid} className="w-full rounded-xl bg-emerald-400 px-4 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50">{loading?"Logging in…":"Log In"}</button><p className="text-center text-sm text-slate-400">Don&apos;t have an account? <Link href="/signup" className="font-semibold text-emerald-400 hover:text-emerald-300">Sign up</Link></p></form></AuthMain>;
}
