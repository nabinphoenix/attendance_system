"use client";

import {useEffect,useRef,useState} from "react";
import {Button} from "./Button";

export function ConfirmDialog({open,title,description,confirmLabel="Confirm",tone="primary",requireReason=false,onClose,onConfirm}:{open:boolean;title:string;description?:string;confirmLabel?:string;tone?:"primary"|"danger";requireReason?:boolean;onClose:()=>void;onConfirm:(reason:string)=>void|Promise<void>}){
  const[reason,setReason]=useState("");const[working,setWorking]=useState(false);const input=useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{if(open){setReason("");window.setTimeout(()=>input.current?.focus(),0)}},[open]);
  useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==="Escape"&&!working)onClose()};window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close)},[open,working,onClose]);
  if(!open)return null;
  async function submit(){if(requireReason&&!reason.trim())return;setWorking(true);try{await onConfirm(reason.trim());onClose()}finally{setWorking(false)}}
  return <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button aria-label="Close dialog" className="absolute inset-0 bg-black/70" onClick={onClose}/><div className="panel relative w-full max-w-md p-6"><h2 id="dialog-title" className="text-xl font-semibold">{title}</h2>{description&&<p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>}{requireReason&&<label className="mt-4 block"><span className="field-label">Reason</span><textarea ref={input} value={reason} onChange={event=>setReason(event.target.value)} rows={3} className="w-full" placeholder="Add a short audit note"/></label>}<div className="mt-6 flex justify-end gap-3"><Button variant="ghost" onClick={onClose} disabled={working}>Cancel</Button><Button variant={tone} loading={working} disabled={requireReason&&!reason.trim()} onClick={()=>void submit()}>{confirmLabel}</Button></div></div></div>;
}
