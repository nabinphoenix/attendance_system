"use client";
import { useEffect, useId, useRef, useState } from "react";
import { trapDialogFocus } from "./dialogFocus";
import { Button } from "./Button";
export function ConfirmDialog({open,title,description,confirmLabel="Confirm",tone="primary",requireReason=false,onClose,onConfirm}:{open:boolean;title:string;description?:string;confirmLabel?:string;tone?:"primary"|"danger";requireReason?:boolean;onClose:()=>void;onConfirm:(reason:string)=>void|Promise<void>}) {
  const [reason,setReason]=useState(""); const [working,setWorking]=useState(false); const [error,setError]=useState("");
  const dialog=useRef<HTMLDialogElement>(null); const titleId=useId();
  useEffect(()=>{if(open){setReason("");setError("");dialog.current?.showModal();const previous=document.body.style.overflow;document.body.style.overflow="hidden";return()=>{document.body.style.overflow=previous;};}else dialog.current?.close();},[open]);
  async function submit(){if(requireReason&&!reason.trim())return;setWorking(true);setError("");try{await onConfirm(reason.trim());onClose();}catch{setError("We could not complete this action. Please try again.");}finally{setWorking(false);}}
  return <dialog onKeyDown={trapDialogFocus} ref={dialog} aria-labelledby={titleId} onClose={onClose} onCancel={event=>{if(working)event.preventDefault();else onClose();}} className="panel m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-md overflow-y-auto p-5 text-inherit sm:p-6">
    <h2 id={titleId} className="text-xl font-semibold">{title}</h2>{description&&<p className="app-caption mt-2 break-words text-sm leading-6">{description}</p>}
    {error&&<p role="alert" className="mt-3 text-sm text-red-500">{error}</p>}
    {requireReason&&<label className="mt-4 block"><span className="field-label">Reason</span><textarea value={reason} onChange={event=>setReason(event.target.value)} rows={3} placeholder="Add a short audit note"/></label>}
    <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><Button variant="ghost" onClick={onClose} disabled={working}>Cancel</Button><Button variant={tone} loading={working} disabled={requireReason&&!reason.trim()} onClick={()=>void submit()}>{confirmLabel}</Button></div>
  </dialog>;
}
