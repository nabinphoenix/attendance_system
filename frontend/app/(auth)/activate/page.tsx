"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import api from "@/lib/api";
import { AuthMain, Field } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type ActivationInfo = {
  student_name: string;
  email: string;
  mode: "activation" | "password_setup";
  account_exists: boolean;
};

function ActivateAccount() {
  const token = useSearchParams().get("token") || "";
  const router = useRouter();
  const [info, setInfo] = useState<ActivationInfo | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const passwordSetup = info?.mode === "password_setup";

  useEffect(() => {
    if (!token) {
      setError("Invitation token is missing.");
      return;
    }
    api.get<ActivationInfo>(`/api/v1/auth/activate/validate?token=${encodeURIComponent(token)}`)
      .then((response) => setInfo(response.data))
      .catch(() => setError("This invitation is invalid or has expired."));
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.post("/api/v1/auth/activate", { token, password });
      setDone(true);
      window.setTimeout(() => router.push("/student/dashboard"), 700);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Your password could not be saved. Check the invitation and try again.");
    } finally {
      setLoading(false);
    }
  }

  return <AuthMain>
    <form onSubmit={submit} className="space-y-5">
      <header>
        <p className="text-sm font-semibold text-emerald-400">SECURE STUDENT ACCOUNT SETUP</p>
        <h1 className="mt-2 text-3xl font-semibold">{passwordSetup ? "Set your account password" : "Activate your account"}</h1>
        {info && <>
          <p className="mt-2 text-slate-400">{info.student_name} · {info.email}</p>
          {passwordSetup && <p className="mt-2 text-sm leading-6 text-slate-400">Your account and attendance data are already active. Saving this form replaces the temporary or current password.</p>}
        </>}
      </header>
      {error && <SystemFeedback tone="danger" title="Account setup could not be completed" description={error} />}
      {done
        ? <SystemFeedback tone="success" title={passwordSetup ? "Password updated" : "Account activated"} description="Signing you in…" />
        : info && <>
          <Field label="Choose a password" hint="Use at least 8 characters." error="">
            <PasswordInput required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} className="w-full" autoComplete="new-password" />
          </Field>
          <Button type="submit" className="w-full" size="lg" loading={loading}>{loading ? "Saving…" : passwordSetup ? "Save password" : "Activate account"}</Button>
        </>}
    </form>
  </AuthMain>;
}

export default function Page() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center text-sm text-slate-400">Loading invitation…</main>}>
    <ActivateAccount />
  </Suspense>;
}
