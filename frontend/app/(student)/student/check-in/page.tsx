"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { getBestFreshPosition, hasSecureDeviceContext, locationFailureReason } from "@/lib/geolocation";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

type Stage = "ready" | "checking" | "locating" | "verifying" | "success" | "pending" | "error";
type Result = { message: string; module_title: string; room: string; start_time: string; reason?: string };

const stages: Record<Stage, { title: string; description: string; tone: string; symbol: string }> = {
  ready: { title: "Ready to check in", description: "Scan the current QR shown by your teacher.", tone: "border-slate-700 bg-slate-900", symbol: "1" },
  checking: { title: "Verifying QR…", description: "Checking that this classroom code is current and secure.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  locating: { title: "Getting your location…", description: "Waiting briefly for the best fresh reading.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  verifying: { title: "Checking classroom presence…", description: "Comparing your location with this attendance session.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  success: { title: "Attendance recorded", description: "You’re checked in for this class.", tone: "border-emerald-500/30 bg-emerald-500/10", symbol: "✓" },
  pending: { title: "Location couldn’t be verified", description: "Your check-in was sent to your teacher for confirmation.", tone: "border-amber-500/30 bg-amber-500/10", symbol: "!" },
  error: { title: "Check-in couldn’t be completed", description: "Review the message below and try the latest classroom QR.", tone: "border-red-500/30 bg-red-500/10", symbol: "!" },
};

const emptyResult = (message: string): Result => ({ message, module_title: "", room: "", start_time: "" });

export default function Page() {
  const [token, setToken] = useState("");
  const [stage, setStage] = useState<Stage>("ready");
  const [result, setResult] = useState<Result | null>(null);
  const [camera, setCamera] = useState(false);
  const [permissionReady, setPermissionReady] = useState(false);
  const scanner = useRef<{ stop: () => Promise<void>; clear: () => void } | null>(null);

  useEffect(() => () => { scanner.current?.stop().catch(() => undefined); }, []);

  function secureConnectionRequired() {
    setPermissionReady(true);
    setResult(emptyResult("QR camera and location verification require HTTPS on a phone. Open AntimBench using its secure HTTPS address, then try again."));
    setStage("error");
  }

  async function submitToken(qrToken: string) {
    if (!qrToken.trim()) return;
    if (!hasSecureDeviceContext()) {
      secureConnectionRequired();
      return;
    }

    setResult(null);
    setStage("checking");
    let payload: Record<string, unknown> = { qr_token: qrToken.trim() };
    try {
      setStage("locating");
      const position = await getBestFreshPosition();
      payload = {
        ...payload,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      };
    } catch (error) {
      payload = { ...payload, location_failure_reason: locationFailureReason(error) };
    }

    try {
      setStage("verifying");
      const { data } = await api.post<Result & { status: "present" | "pending_verification" }>("/api/v1/check-ins", payload);
      setResult(data);
      setStage(data.status === "present" ? "success" : "pending");
    } catch (error: any) {
      const detail = String(error.response?.data?.detail ?? "");
      const friendly: Record<string, string> = {
        QR_EXPIRED: "This QR has expired. Scan the latest QR shown by your teacher.",
        INVALID_QR: "This QR is invalid. Scan the latest classroom code again.",
        ALREADY_CHECKED_IN: "Your attendance is already recorded for this session.",
        STUDENT_NOT_ELIGIBLE: "This class is not assigned to your section.",
        SESSION_FINALIZED: "This attendance session has already closed.",
        SESSION_CANCELLED: "This class has been cancelled.",
        ATTENDANCE_WINDOW_CLOSED: "The attendance window for this session has closed.",
      };
      setResult(emptyResult(friendly[detail] ?? "Check-in could not be completed. Please ask your teacher for help."));
      setStage("error");
    }
  }

  async function startCamera() {
    if (!hasSecureDeviceContext()) {
      secureConnectionRequired();
      return;
    }
    setCamera(true);
    setStage("ready");
    try {
      const { Html5Qrcode } = await import("html5-qrcode");
      const reader = new Html5Qrcode("attendance-qr-reader");
      scanner.current = reader;
      await reader.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        async (decoded) => {
          setToken(decoded);
          await reader.stop();
          reader.clear();
          scanner.current = null;
          setCamera(false);
          await submitToken(decoded);
        },
        () => undefined,
      );
    } catch {
      scanner.current = null;
      setCamera(false);
      setResult(emptyResult("Camera access is unavailable. Allow camera access or use the manual option below."));
      setStage("error");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void submitToken(token);
  }

  const busy = ["checking", "locating", "verifying"].includes(stage);
  const current = stages[stage];

  return <div className="mx-auto max-w-2xl">
    <PageHeader title="Attendance check-in" description="Scan your teacher’s current QR and verify that you are near the class." />
    {!permissionReady ? <section className="panel p-6 text-center sm:p-8">
      <span aria-hidden="true" className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-xl text-emerald-300">⌖</span>
      <h2 className="mt-4 text-xl font-semibold">Location verification</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">AntimBench uses your current location only to verify that you are near the class when checking in.</p>
      <Button className="mt-6 w-full sm:w-auto" size="lg" onClick={() => hasSecureDeviceContext() ? setPermissionReady(true) : secureConnectionRequired()}>Continue</Button>
    </section> : <>
      <section aria-live="polite" className={`rounded-xl border p-4 sm:p-5 ${current.tone}`}>
        <div className="flex items-start gap-3 sm:gap-4">
          <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-current font-semibold">{busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" /> : current.symbol}</span>
          <div className="min-w-0"><h2 className="font-semibold">{current.title}</h2><p className="mt-1 text-sm leading-5 text-slate-300/80">{current.description}</p>{result?.message && result.message !== current.description && <p className="mt-2 text-sm font-medium leading-5">{result.message}</p>}{result?.module_title && <div className="mt-4 border-t border-current/15 pt-3"><p className="font-semibold">{result.module_title}</p><p className="mt-1 text-sm">{result.start_time.slice(0, 5)} · Room {result.room}</p></div>}</div>
        </div>
      </section>
      <section className="panel mt-5 p-4 sm:p-6">
        <Button className="w-full" size="lg" onClick={() => void startCamera()} disabled={camera || busy}>{camera ? "Camera active…" : "Scan classroom QR"}</Button>
        {camera && <div id="attendance-qr-reader" className="mt-4 overflow-hidden rounded-lg bg-white" />}
        <details className="mt-5 border-t border-slate-800 pt-4"><summary className="cursor-pointer text-sm font-medium text-slate-400 hover:text-slate-200">Camera unavailable? Enter the QR token manually</summary><form onSubmit={submit} className="mt-4 space-y-3"><label className="field-label" htmlFor="qr-token">QR token</label><textarea id="qr-token" value={token} onChange={(event) => setToken(event.target.value)} className="h-24 w-full" required /><Button type="submit" variant="secondary" disabled={busy} className="w-full sm:w-auto">Verify and check in</Button></form></details>
      </section>
    </>}
  </div>;
}
