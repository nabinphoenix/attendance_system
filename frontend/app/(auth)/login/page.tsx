"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { jwtDecode } from "jwt-decode";
import api from "@/lib/api";
import { storeToken, type Role } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
export default function LoginPage() {
  const router=useRouter(); const [email,setEmail]=useState(""); const [password,setPassword]=useState(""); const [error,setError]=useState("");
  async function submit(e:FormEvent){e.preventDefault();setError("");try{const {data}=await api.post("/api/v1/auth/login",{email,password});storeToken(data.access_token);const role=jwtDecode<{role:Role}>(data.access_token).role;router.push(role==="teacher"?"/teacher/sessions":role==="student"?"/student/check-in":`/${role}/dashboard`)}catch(err:any){setError(err.response?.data?.detail??"Login failed")}}
  return <main className="grid min-h-screen place-items-center"><form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-800 p-6"><h1 className="text-2xl font-bold">Sign in</h1><input value={email} onChange={e=>setEmail(e.target.value)} className="w-full rounded bg-slate-800 p-3" type="email" placeholder="Email" required/><input value={password} onChange={e=>setPassword(e.target.value)} className="w-full rounded bg-slate-800 p-3" type="password" placeholder="Password" required/>{error&&<p className="text-red-400">{error}</p>}<Button type="submit">Continue</Button><p className="text-xs text-slate-500">Demo note: the access token is stored in localStorage for this hackathon slice. Production should use a same-origin BFF with Secure, HttpOnly cookies.</p></form></main>;
}
