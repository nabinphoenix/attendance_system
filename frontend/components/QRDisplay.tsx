"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

const qrProps = {
  level: "L" as const,
  // Keep the compact L-level payload for the largest modules at distance, but
  // let the QR encoder use a stronger correction level when it fits the same
  // QR version. This improves glare/occlusion tolerance without densifying
  // the code unnecessarily.
  boostLevel: true,
  marginSize: 4,
  bgColor: "#FFFFFF",
  fgColor: "#000000",
  shapeRendering: "crispEdges" as const,
};

export default function QRDisplay({ value, classroomCode, size = 520 }: { value: string; classroomCode: string; size?: number }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return <>
    <button type="button" onClick={() => setOpen(true)} aria-label="Open full-screen attendance QR code" className="group mx-auto block w-full max-w-[560px] rounded-xl bg-white p-4 text-left shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:ring-4 hover:ring-emerald-400/50 focus-visible:ring-4 focus-visible:ring-emerald-400 sm:p-6">
      <QRCodeSVG value={value} size={size} title="Attendance QR code" {...qrProps} className="h-auto w-full" />
      <span className="mt-3 flex items-center justify-center gap-2 text-sm font-semibold text-slate-700"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /></svg>Open projector scan view</span>
    </button>
    {open && <div role="dialog" aria-modal="true" aria-label="Full-screen attendance QR code" className="fixed inset-0 z-[80] grid place-items-center bg-slate-950/95 p-4 backdrop-blur-sm">
      <button type="button" aria-label="Close full-screen QR code" onClick={() => setOpen(false)} className="absolute right-4 top-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 text-sm font-semibold text-slate-100 transition hover:border-slate-400 hover:bg-slate-800"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg>Close</button>
      <div className="w-full max-w-[min(96rem,calc(100vh-10rem),calc(100vw-2rem))] rounded-2xl bg-white p-3 shadow-2xl sm:p-4"><QRCodeSVG value={value} size={1800} title="Attendance QR code" {...qrProps} className="h-auto w-full" /><div className="mt-3 border-t border-slate-200 pt-3 text-center"><p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Attendance code · alternative to QR</p><p className="mt-1 font-mono text-2xl font-bold tracking-[0.15em] sm:text-4xl sm:tracking-[0.3em] text-slate-900">{classroomCode}</p></div><p className="mt-3 text-center text-sm font-semibold text-slate-700">High-contrast projector scan view · keep the full white border visible</p></div>
    </div>}
  </>;
}
