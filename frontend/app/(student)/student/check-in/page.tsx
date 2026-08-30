"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { getBestFreshPosition, hasSecureDeviceContext, locationFailureReason } from "@/lib/geolocation";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

type Stage = "ready" | "checking" | "locating" | "verifying" | "code" | "success" | "pending" | "error";
type Result = { message: string; module_title: string; room: string; start_time: string; reason?: string };
type ScanResult = Result & { status: "challenge_required" | "pending_verification"; verification_token?: string; verification_expires_at?: string; code_length?: number };

const stages: Record<Stage, { title: string; description: string; tone: string; symbol: string }> = {
  ready: { title: "Ready to check in", description: "Scan the current QR shown by your teacher.", tone: "border-slate-700 bg-slate-900", symbol: "1" },
  checking: { title: "Verifying QR…", description: "Checking that this classroom code is current and secure.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  locating: { title: "Getting your location…", description: "Checking that you are within the campus attendance area.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  verifying: { title: "Preparing classroom verification…", description: "Your QR scan is being verified.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  code: { title: "QR verified", description: "Enter the five-digit code announced by your teacher.", tone: "border-emerald-500/30 bg-emerald-500/10", symbol: "2" },
  success: { title: "Attendance recorded", description: "Your attendance has been recorded successfully.", tone: "border-emerald-500/30 bg-emerald-500/10", symbol: "✓" },
  pending: { title: "Location couldn’t be verified", description: "Your check-in was sent to your teacher for confirmation.", tone: "border-amber-500/30 bg-amber-500/10", symbol: "!" },
  error: { title: "Check-in couldn’t be completed", description: "Scan the current classroom QR and try again.", tone: "border-red-500/30 bg-red-500/10", symbol: "!" },
};

const emptyResult = (message: string): Result => ({ message, module_title: "", room: "", start_time: "" });

export default function Page() {
  const [stage, setStage] = useState<Stage>("ready");
  const [result, setResult] = useState<Result | null>(null);
  const [camera, setCamera] = useState(false);
  const [permissionReady, setPermissionReady] = useState(false);
  const [verificationToken, setVerificationToken] = useState("");
  const [verificationExpiresAt, setVerificationExpiresAt] = useState("");
  const [code, setCode] = useState("");
  const [codeLength, setCodeLength] = useState(5);
  const [countdown, setCountdown] = useState(0);
  const scanner = useRef<{ stop: () => Promise<void>; clear: () => void } | null>(null);

  useEffect(() => () => { scanner.current?.stop().catch(() => undefined); }, []);
  useEffect(() => {
    const update = () => setCountdown(verificationExpiresAt ? Math.max(0, Math.ceil((new Date(verificationExpiresAt).getTime() - Date.now()) / 1000)) : 0);
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [verificationExpiresAt]);

  function secureConnectionRequired() {
    setPermissionReady(true);
    setResult(emptyResult("QR camera and campus location verification require HTTPS on your phone. Open AntimBench using its secure HTTPS address, then try again."));
    setStage("error");
  }

  function resetToScan(message: string) {
    setVerificationToken("");
    setVerificationExpiresAt("");
    setCode("");
    setResult(emptyResult(message));
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
      payload = { ...payload, latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy };
    } catch (error) {
      payload = { ...payload, location_failure_reason: locationFailureReason(error) };
    }
    try {
      setStage("verifying");
      const { data } = await api.post<ScanResult>("/api/v1/check-ins", payload);
      setResult(data);
      if (data.status === "challenge_required" && data.verification_token && data.verification_expires_at) {
        setVerificationToken(data.verification_token);
        setVerificationExpiresAt(data.verification_expires_at);
        setCodeLength(data.code_length ?? 5);
        setCode("");
        setStage("code");
      } else setStage("pending");
    } catch (error: any) {
      const detail = String(error.response?.data?.detail ?? "");
      const friendly: Record<string, string> = {
        QR_EXPIRED: "This QR has expired. Scan the latest QR shown by your teacher.",
        INVALID_QR: "This QR is invalid. Scan the current classroom QR again.",
        ATTENDANCE_CHALLENGE_EXPIRED: "This classroom challenge has expired. Scan the current QR again.",
        ALREADY_CHECKED_IN: "Your attendance is already recorded for this session.",
        STUDENT_NOT_ELIGIBLE: "This class is not assigned to your section.",
        SESSION_FINALIZED: "This attendance session has already closed.",
        SESSION_CANCELLED: "This class has been cancelled.",
        SELF_CHECKIN_WINDOW_CLOSED: "The self check-in window has closed. Ask your teacher for help.",
      };
      resetToScan(friendly[detail] ?? "Check-in could not be completed. Please ask your teacher for help.");
    }
  }

  async function confirmAttendance(event: FormEvent) {
    event.preventDefault();
    if (!verificationToken || code.length !== codeLength) return;
    try {
      setStage("verifying");
      const { data } = await api.post<Result>("/api/v1/check-ins/confirm", { verification_token: verificationToken, code });
      setVerificationToken("");
      setVerificationExpiresAt("");
      setResult(data);
      setStage("success");
    } catch (error: any) {
      const detail = String(error.response?.data?.detail ?? "");
      if (detail.startsWith("INCORRECT_CLASSROOM_CODE:")) {
        const remaining = detail.split(":")[1];
        setResult(emptyResult(`Incorrect classroom code. ${remaining} attempt${remaining === "1" ? "" : "s"} remaining.`));
        setStage("code");
        return;
      }
      if (detail === "ATTENDANCE_CHALLENGE_EXPIRED" || detail === "VERIFICATION_FAILED") {
        resetToScan("This classroom challenge is no longer valid. Scan the current QR again.");
        return;
      }
      if (detail === "ALREADY_CHECKED_IN") {
        setVerificationToken("");
        setVerificationExpiresAt("");
        setResult(emptyResult("Your attendance is already recorded for this session."));
        setStage("success");
        return;
      }
      resetToScan("Attendance could not be verified. Scan the current QR and try again.");
    }
  }

  async function startCamera() {
    if (!hasSecureDeviceContext()) {
      secureConnectionRequired();
      return;
    }
    setCamera(true);
    setStage("ready");
    setResult(null);
    try {
      const { Html5Qrcode } = await import("html5-qrcode");
      const reader = new Html5Qrcode("attendance-qr-reader");
      scanner.current = reader;
      await reader.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        async (decoded) => {
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
      resetToScan("Camera access is unavailable. Ask your teacher to use manual attendance.");
    }
  }

  const busy = ["checking", "locating", "verifying"].includes(stage);
  const current = stages[stage];

  return <div className="mx-auto max-w-2xl">
    <PageHeader title="Attendance check-in" description="Scan your teacher’s current QR, then enter the spoken classroom code." />
    {!permissionReady ? <section className="panel p-6 text-center sm:p-8">
      <span aria-hidden="true" className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-xl text-emerald-300">⌖</span>
      <h2 className="mt-4 text-xl font-semibold">Classroom verification</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">AntimBench verifies the current QR, a spoken classroom code, and your campus location before recording attendance.</p>
      <Button className="mt-6 w-full sm:w-auto" size="lg" onClick={() => hasSecureDeviceContext() ? setPermissionReady(true) : secureConnectionRequired()}>Continue</Button>
    </section> : <>
      <section aria-live="polite" className={`rounded-xl border p-4 sm:p-5 ${current.tone}`}>
        <div className="flex items-start gap-3 sm:gap-4">
          <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-current font-semibold">{busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" /> : current.symbol}</span>
          <div className="min-w-0"><h2 className="font-semibold">{current.title}</h2><p className="mt-1 text-sm leading-5 text-slate-300/80">{current.description}</p>{result?.message && result.message !== current.description && <p className="mt-2 text-sm font-medium leading-5">{result.message}</p>}{result?.module_title && <div className="mt-4 border-t border-current/15 pt-3"><p className="font-semibold">{result.module_title}</p><p className="mt-1 text-sm">{result.start_time.slice(0, 5)} · Room {result.room}</p></div>}</div>
        </div>
      </section>
      {stage === "code" && <section className="panel mt-5 p-5 sm:p-6"><form onSubmit={confirmAttendance}><label className="block text-center" htmlFor="classroom-code"><span className="text-sm font-semibold text-slate-200">Enter the {codeLength}-digit code announced by your teacher</span><input id="classroom-code" autoFocus autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]*" maxLength={codeLength} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, codeLength))} className="mx-auto mt-4 block max-w-xs text-center font-mono text-3xl font-bold tracking-[0.45em]" aria-describedby="classroom-code-help" /><span id="classroom-code-help" className="mt-3 block text-sm text-slate-400">Complete verification within {countdown} second{countdown === 1 ? "" : "s"}.</span></label><div className="mt-5 flex justify-center"><Button type="submit" size="lg" disabled={busy || code.length !== codeLength}>Verify Attendance</Button></div></form></section>}
      {stage !== "code" && <section className="panel mt-5 p-4 sm:p-6"><Button className="w-full" size="lg" onClick={() => void startCamera()} disabled={camera || busy || stage === "success" || stage === "pending"}>{camera ? "Camera active…" : "Scan classroom QR"}</Button>{camera && <div id="attendance-qr-reader" className="mt-4 overflow-hidden rounded-lg bg-white" />}{stage === "error" && <p className="mt-4 text-center text-sm text-slate-400">The QR and spoken code are both required. Camera problems must be handled through teacher-controlled manual attendance.</p>}</section>}
    </>}
  </div>;
}
