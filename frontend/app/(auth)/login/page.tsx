"use client";
import { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
export default function LoginPage() { function submit(e: FormEvent) { e.preventDefault(); } return <main className="grid min-h-screen place-items-center"><form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-800 p-6"><h1 className="text-2xl font-bold">Sign in</h1><input className="w-full rounded bg-slate-800 p-3" type="email" placeholder="Email" /><input className="w-full rounded bg-slate-800 p-3" type="password" placeholder="Password" /><Button type="submit">Continue</Button></form></main>; }

