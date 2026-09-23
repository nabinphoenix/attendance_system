"use client";
import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
export function UnlockAccountButton({id,name,platform=false,onUnlocked}:{id:number;name:string;platform?:boolean;onUnlocked:()=>void|Promise<void>}){
  const [open,setOpen]=useState(false);
  return <><Button size="sm" variant="outline" onClick={()=>setOpen(true)}>Unlock account</Button><ConfirmDialog open={open} title="Unlock account?" description={`Allow ${name} to sign in again with their existing password. Their password will stay the same.`} confirmLabel="Unlock account" onClose={()=>setOpen(false)} onConfirm={async()=>{await api.post(`/api/v1/${platform?"platform/":""}users/${id}/unlock`);await onUnlocked();}}/></>;
}
