"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

export default function QRDisplay({ value, size = 340 }: { value: string; size?: number }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return <>
    <button type="button" onClick={() => setOpen(true)} aria-label="Open full-screen attendance QR code" className="group mx-auto block w-full max-w-[380px] rounded-xl bg-white p-5 text-left shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:ring-4 hover:ring-emerald-400/50 focus-visible:ring-4 focus-visible:ring-emerald-400">
      <QRCodeSVG value={value} size={size} level="M" className="h-auto w-full" />
      <span className="mt-3 flex items-center justify-center gap-2 text-sm font-semibold text-slate-700"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /></svg>Tap to show full-screen QR</span>
    </button>
    {open && <div role="dialog" aria-modal="true" aria-label="Full-screen attendance QR code" className="fixed inset-0 z-[80] grid place-items-center bg-slate-950/95 p-4 backdrop-blur-sm">
      <button type="button" aria-label="Close full-screen QR code" onClick={() => setOpen(false)} className="absolute right-4 top-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 text-sm font-semibold text-slate-100 transition hover:border-slate-400 hover:bg-slate-800"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg>Close</button>
      <div className="w-full max-w-[min(44rem,calc(100vh-9rem))] rounded-2xl bg-white p-5 shadow-2xl sm:p-8"><QRCodeSVG value={value} size={720} level="M" className="h-auto w-full" /><p className="mt-5 text-center text-sm font-semibold text-slate-700">Students can scan this full-screen QR code now</p></div>
    </div>}
  </>;
}
