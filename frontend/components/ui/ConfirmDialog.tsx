"use client";
import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";
import { trapDialogFocus } from "./dialogFocus";
import { Button } from "./Button";

function DialogIcon({ tone }: { tone: "primary" | "danger" }) {
  return tone === "danger"
    ? <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 8v4m0 4h.01M5.2 19h13.6c1.1 0 1.8-1.2 1.3-2.1L13.3 5.1a1.5 1.5 0 0 0-2.6 0L3.9 16.9c-.5.9.2 2.1 1.3 2.1Z" /></svg>
    : <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 8v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
}

export function ConfirmDialog({open,title,description,confirmLabel="Confirm",tone="primary",requireReason=false,children,onClose,onConfirm}:{open:boolean;title:string;description?:string;confirmLabel?:string;tone?:"primary"|"danger";requireReason?:boolean;children?:ReactNode;onClose:()=>void;onConfirm:(reason:string)=>void|Promise<void>}) {
  const [reason,setReason]=useState(""); const [working,setWorking]=useState(false); const [error,setError]=useState("");
  const dialog=useRef<HTMLDialogElement>(null); const titleId=useId(); const descriptionId=useId();
  useEffect(()=>{if(open){setReason("");setError("");dialog.current?.showModal();const previous=document.body.style.overflow;document.body.style.overflow="hidden";return()=>{document.body.style.overflow=previous;};}else dialog.current?.close();},[open]);
  async function submit(){if(requireReason&&!reason.trim())return;setWorking(true);setError("");try{await onConfirm(reason.trim());onClose();}catch{setError("We could not complete this action. Please try again.");}finally{setWorking(false);}}
  return <dialog onKeyDown={trapDialogFocus} ref={dialog} aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} onClose={onClose} onCancel={event=>{if(working)event.preventDefault();else onClose();}} className="confirm-dialog text-inherit">
    <div className="relative p-5 sm:p-6">
      <button type="button" aria-label="Close dialog" onClick={onClose} disabled={working} className="confirm-dialog-close absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-lg border border-transparent transition disabled:cursor-not-allowed disabled:opacity-50"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
      <div className="flex items-start gap-3 pr-10">
        <span className={`confirm-dialog-icon grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${tone === "danger" ? "confirm-dialog-icon-danger" : "confirm-dialog-icon-primary"}`}><span className="h-5 w-5"><DialogIcon tone={tone} /></span></span>
        <div className="min-w-0"><h2 id={titleId} className="text-lg font-semibold leading-7 sm:text-xl">{title}</h2>{description&&<p id={descriptionId} className="app-caption mt-1.5 break-words text-sm leading-6">{description}</p>}</div>
      </div>
      {children&&<div className="mt-5">{children}</div>}
      {error&&<p role="alert" className="confirm-dialog-error mt-4 rounded-lg border px-3 py-2 text-sm">{error}</p>}
      {requireReason&&<label className="mt-5 block"><span className="field-label">Reason</span><textarea value={reason} onChange={event=>setReason(event.target.value)} rows={3} placeholder="Add a short audit note"/></label>}
    </div>
    <div className="confirm-dialog-footer flex flex-col-reverse gap-2 border-t px-5 py-4 sm:flex-row sm:justify-end sm:px-6"><Button className="w-full sm:w-auto" variant="ghost" onClick={onClose} disabled={working}>Cancel</Button><Button className="w-full sm:w-auto" variant={tone} loading={working} disabled={requireReason&&!reason.trim()} onClick={()=>void submit()}>{confirmLabel}</Button></div>
  </dialog>;
}
