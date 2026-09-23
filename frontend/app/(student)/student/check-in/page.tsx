"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { getBestFreshPosition, hasSecureDeviceContext, locationFailureReason } from "@/lib/geolocation";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

type Method = "qr" | "code";
type Stage = "ready" | "checking" | "locating" | "verifying" | "success" | "pending" | "error";
type Result = { message: string; module_title: string; room: string; start_time: string; reason?: string };
type CheckInResult = Result & { status: "challenge_required" | "pending_verification" | "present"; verification_token?: string };

const stages: Record<Stage, { title: string; description: string; tone: string; symbol: string }> = {
  ready: { title: "Ready to check in", description: "Scan the current QR or enter your teacher's attendance code.", tone: "border-slate-700 bg-slate-900", symbol: "1" },
  checking: { title: "Checking attendance…", description: "Verifying the current class session.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  locating: { title: "Getting your location…", description: "Checking that you are within the campus attendance area.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  verifying: { title: "Confirming attendance…", description: "Completing your secure check-in.", tone: "border-blue-500/30 bg-blue-500/10", symbol: "·" },
  success: { title: "Attendance recorded", description: "Your attendance has been recorded successfully.", tone: "border-emerald-500/30 bg-emerald-500/10", symbol: "✓" },
  pending: { title: "Location couldn’t be verified", description: "Your check-in was sent to your teacher for confirmation.", tone: "border-amber-500/30 bg-amber-500/10", symbol: "!" },
  error: { title: "Check-in couldn’t be completed", description: "Please try again or ask your teacher for help.", tone: "border-red-500/30 bg-red-500/10", symbol: "!" },
};

const emptyResult = (message: string): Result => ({ message, module_title: "", room: "", start_time: "" });

export default function Page() {
  const [stage, setStage] = useState<Stage>("ready");
  const [result, setResult] = useState<Result | null>(null);
  const [camera, setCamera] = useState(false);
  const [permissionReady, setPermissionReady] = useState(false);
  const [method, setMethod] = useState<Method | null>(null);
  const [attendanceCode, setAttendanceCode] = useState("");
  const scanner = useRef<{ stop: () => Promise<void>; clear: () => void } | null>(null);
  const scanHandled = useRef(false);
  const scannerGeneration = useRef(0);

  useEffect(() => () => { scannerGeneration.current += 1; scanner.current?.stop().catch(() => undefined); }, []);

  function secureConnectionRequired() {
    setPermissionReady(true);
    setResult(emptyResult("Camera and location verification require HTTPS on your phone. Open AntimBench using its secure HTTPS address, then try again."));
    setStage("error");
  }

  async function submitAttendance(selectedMethod: Method, credential: string) {
    if (!credential.trim()) return;
    if (!hasSecureDeviceContext()) {
      secureConnectionRequired();
      return;
    }
    setMethod(selectedMethod);
    setResult(null);
    setStage("checking");
    let payload: Record<string, unknown> = selectedMethod === "qr" ? { qr_token: credential.trim() } : { attendance_code: credential.trim() };
    try {
      setStage("locating");
      const position = await getBestFreshPosition();
      payload = { ...payload, latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy };
    } catch (error) {
      payload = { ...payload, location_failure_reason: locationFailureReason(error) };
    }
    try {
      setStage("verifying");
      const endpoint = selectedMethod === "qr" ? "/api/v1/check-ins" : "/api/v1/check-ins/code";
      const { data } = await api.post<CheckInResult>(endpoint, payload);
      if (data.status === "challenge_required") {
        if (!data.verification_token) throw new Error("Missing verification token");
        const confirmation = await api.post<Result>("/api/v1/check-ins/confirm", { verification_token: data.verification_token });
        setResult(confirmation.data);
        setStage("success");
      } else if (data.status === "pending_verification") {
        setResult(data);
        setStage("pending");
      } else {
        setResult(data);
        setStage("success");
      }
    } catch (error: any) {
      const detail = String(error.response?.data?.detail ?? "");
      if (detail === "ALREADY_CHECKED_IN") {
        setResult(emptyResult("Your attendance is already recorded for this session."));
        setStage("success");
        return;
      }
      const friendly: Record<string, string> = {
        QR_EXPIRED: "This QR has expired. Scan the latest QR shown by your teacher.",
        INVALID_QR: "This QR is invalid. Scan the current classroom QR again.",
        INVALID_ATTENDANCE_CODE: "That attendance code is invalid. Check the current code shown by your teacher.",
        ATTENDANCE_CODE_EXPIRED: "This attendance code has expired. Ask your teacher for the current code.",
        ATTENDANCE_CHALLENGE_EXPIRED: "This attendance challenge has expired. Try the current QR or attendance code again.",
        VERIFICATION_FAILED: "This verification is no longer valid. Try again.",
        STUDENT_NOT_ELIGIBLE: "This class is not assigned to your section.",
        SESSION_FINALIZED: "This attendance session has already closed.",
        SESSION_CANCELLED: "This class has been cancelled.",
        SELF_CHECKIN_WINDOW_CLOSED: "The self check-in window has closed. Ask your teacher for help.",
      };
      setResult(emptyResult(friendly[detail] ?? "Check-in could not be completed. Please ask your teacher for help."));
      setStage("error");
    }
  }

  function submitCode(event: FormEvent) {
    event.preventDefault();
    if (/^\d{6}$/.test(attendanceCode)) void submitAttendance("code", attendanceCode);
  }

  async function openCode() {
    scannerGeneration.current += 1;
    if (scanner.current) {
      const reader = scanner.current;
      scanner.current = null;
      await reader.stop().catch(() => undefined);
      reader.clear();
    }
    setCamera(false);
    setMethod("code");
    setStage("ready");
    setResult(null);
  }

  async function startCamera() {
    if (!hasSecureDeviceContext()) {
      secureConnectionRequired();
      return;
    }
    setMethod("qr");
    setCamera(true);
    setStage("ready");
    setResult(null);
    scanHandled.current = false;
    const generation = ++scannerGeneration.current;
    try {
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import("html5-qrcode");
      if (generation !== scannerGeneration.current) return;
      const reader = new Html5Qrcode("attendance-qr-reader", { verbose: false, formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE], useBarCodeDetectorIfSupported: true });
      scanner.current = reader;
      await reader.start(
        { facingMode: "environment" },
        {
          // A large scan box and a higher decode cadence help students scan a
          // projector-sized QR from the back of the room without cropping its
          // quiet zone.
          fps: 15,
          qrbox: (viewfinderWidth, viewfinderHeight) => {
            const side = Math.floor(Math.min(viewfinderWidth, viewfinderHeight) * 0.96);
            return { width: side, height: side };
          },
          videoConstraints: {
            facingMode: { ideal: "environment" },
            width: { ideal: 2560 },
            height: { ideal: 1440 },
          },
        },
        async (decoded) => {
          if (generation !== scannerGeneration.current || scanHandled.current) return;
          scanHandled.current = true;
          await reader.stop();
          reader.clear();
          scanner.current = null;
          setCamera(false);
          await submitAttendance("qr", decoded);
        },
        () => undefined,
      );
      if (generation !== scannerGeneration.current) {
        await reader.stop().catch(() => undefined);
        reader.clear();
      }
    } catch {
      if (generation !== scannerGeneration.current) return;
      scanner.current = null;
      setCamera(false);
      setResult(emptyResult("Camera access is unavailable. Enter the attendance code instead, or ask your teacher for help."));
      setStage("error");
    }
  }

  const busy = ["checking", "locating", "verifying"].includes(stage);
  const finished = stage === "success" || stage === "pending";
  const current = stages[stage];

  return <div className="mx-auto max-w-2xl">
    <PageHeader title="Mark attendance" description="Scan your teacher’s current QR or enter the attendance code. Your location is checked automatically for either option." />
    {!permissionReady ? <section className="panel p-6 text-center sm:p-8">
      <span aria-hidden="true" className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-xl text-emerald-300">⌖</span>
      <h2 className="mt-4 text-xl font-semibold">Classroom verification</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">Choose QR scanning or an attendance code. AntimBench checks your location automatically before recording attendance.</p>
      <Button className="mt-6 w-full sm:w-auto" size="lg" onClick={() => hasSecureDeviceContext() ? setPermissionReady(true) : secureConnectionRequired()}>Continue</Button>
    </section> : <>
      <section aria-live="polite" className={`rounded-xl border p-4 sm:p-5 ${current.tone}`}>
        <div className="flex items-start gap-3 sm:gap-4">
          <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-current font-semibold">{busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" /> : current.symbol}</span>
          <div className="min-w-0"><h2 className="font-semibold">{current.title}</h2><p className="mt-1 text-sm leading-5 text-slate-300/80">{current.description}</p>{result?.message && result.message !== current.description && <p className="mt-2 text-sm font-medium leading-5">{result.message}</p>}{result?.module_title && <div className="mt-4 border-t border-current/15 pt-3"><p className="font-semibold">{result.module_title}</p><p className="mt-1 text-sm">{result.start_time.slice(0, 5)} · Room {result.room}</p></div>}</div>
        </div>
      </section>
      {!finished && <section className="panel mt-5 p-4 sm:p-6">
        <Button className="w-full" size="lg" onClick={() => void startCamera()} disabled={camera || busy}>{camera ? "Camera active…" : "Scan QR"}</Button>
        {camera && <div id="attendance-qr-reader" className="mt-4 overflow-hidden rounded-lg bg-white" />}
        <div className="my-6 flex items-center gap-3 text-xs font-semibold uppercase tracking-wider text-slate-400"><span className="h-px flex-1 bg-slate-700" />OR<span className="h-px flex-1 bg-slate-700" /></div>
        <div className="text-center"><p className="text-sm text-slate-300">Can’t scan the QR?</p><Button className="mt-3 w-full" size="lg" variant="outline" onClick={() => void openCode()} disabled={busy}>Enter Attendance Code</Button></div>
        {method === "code" && <form onSubmit={submitCode} className="mt-5 border-t border-slate-700 pt-5"><label className="block text-sm font-semibold text-slate-200" htmlFor="attendance-code">Six-digit attendance code</label><input id="attendance-code" autoFocus autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={attendanceCode} onChange={(event) => setAttendanceCode(event.target.value.replace(/\D/g, "").slice(0, 6))} className="mt-3 w-full text-center font-mono text-2xl font-bold tracking-[0.3em] sm:text-3xl" /><Button type="submit" className="mt-4 w-full" size="lg" disabled={busy || attendanceCode.length !== 6}>Mark Attendance</Button></form>}
      </section>}
    </>}
  </div>;
}
