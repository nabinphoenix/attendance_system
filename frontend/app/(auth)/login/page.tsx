"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { type Role } from "@/lib/auth";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { AuthMain, Field } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";

const input = "w-full bg-slate-950 px-3 py-3";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const emailError = touched && (!email.trim()
    ? "Email is required"
    : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
      ? "Enter a valid email address"
      : "");
  const passwordError = touched && !password ? "Password is required" : "";
  const invalid = !!emailError || !!passwordError;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    setError("");
    if (!email || !password || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;

    setLoading(true);
    try {
      await api.post("/api/v1/auth/login", { email: email.trim().toLowerCase(), password });
      const { data: user } = await api.get<{ role: Role }>("/api/v1/auth/me");
      const destinations: Record<Role, string> = {
        admin: "/admin/dashboard",
        teacher: "/teacher/sessions",
        student: "/student/dashboard",
        coordinator: "/coordinator/cases",
        parent: "/parent/notifications",
      };
      router.replace(destinations[user.role]);
    } catch (requestError: any) {
      if (requestError.response?.status === 401) {
        setError("Check your email and password, then try again.");
      } else if (!requestError.response) {
        setError("We could not reach AntimBench. Make sure this phone is on the college Wi-Fi and reopen the address provided by your administrator.");
      } else {
        setError("The sign-in service is temporarily unavailable. Please try again in a moment.");
      }
    } finally {
      setLoading(false);
    }
  }

  return <AuthMain split>
    <form noValidate onSubmit={submit} className="mx-auto max-w-md space-y-5">
      <header>
        <p className="text-sm font-semibold text-emerald-400">WELCOME BACK</p>
        <h1 className="mt-2 text-3xl font-semibold">Sign in to AntimBench</h1>
        <p className="mt-2 text-slate-400">Use your college account to continue.</p>
      </header>
      {error && <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
        <p className="font-medium">We couldn&apos;t sign you in</p>
        <p className="mt-1 leading-5 text-red-200/80">{error}</p>
      </div>}
      <Field label="Email address" error={emailError}>
        <input value={email} onChange={(event) => setEmail(event.target.value)} onBlur={() => setTouched(true)} className={`${input} ${emailError ? "border-red-500" : ""}`} type="email" inputMode="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder="name@cps.edu.np" aria-invalid={!!emailError} />
      </Field>
      <Field label="Password" error={passwordError}>
        <PasswordInput value={password} onChange={(event) => setPassword(event.target.value)} onBlur={() => setTouched(true)} className={`${input} ${passwordError ? "border-red-500" : ""}`} autoComplete="current-password" placeholder="Enter your password" aria-invalid={!!passwordError} />
      </Field>
      <p className="rounded-lg bg-slate-950/70 px-3 py-2 text-xs leading-5 text-slate-400">On a phone, use the college Wi-Fi and the AntimBench address provided by your administrator.</p>
      <div className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:justify-between sm:gap-3"><span className="text-slate-500">Need access help?</span><span className="text-slate-300">Contact your college administrator</span></div>
      <Button type="submit" size="lg" loading={loading} disabled={invalid} className="w-full">{loading ? "Signing in…" : "Sign in"}</Button>
      <p className="text-center text-sm text-slate-400">Account access is managed by your college administrator.</p>
    </form>
  </AuthMain>;
}
