"use client";
import { FormEvent, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Field, Heading, Notice, errorMessage, inputClass } from "@/components/PlatformUI";
type Config={platform_name:string;support_email:string|null;allow_college_creation:boolean};
export default function Configuration(){
 const [config,setConfig]=useState<Config|null>(null);const [error,setError]=useState("");const [success,setSuccess]=useState("");const [saving,setSaving]=useState(false);
 useEffect(()=>{api.get("/api/v1/platform/configuration").then(r=>setConfig(r.data)).catch(e=>setError(errorMessage(e)));},[]);
 async function save(e:FormEvent){e.preventDefault();setSaving(true);setError("");setSuccess("");try{const r=await api.put("/api/v1/platform/configuration",{...config,support_email:config?.support_email||null});setConfig(r.data);setSuccess("Platform configuration saved. This change is recorded in the system audit log.");}catch(e){setError(errorMessage(e));}finally{setSaving(false);}}
 return <><Heading title="Platform configuration">Manage shared platform settings. College academic and attendance data is managed in each college?s workspace.</Heading><Notice error={error} success={success}/>{!config&&!error?<p role="status">Loading configuration?</p>:config&&<form className="panel max-w-2xl space-y-5 p-6" onSubmit={save}><Field label="Platform name"><input required maxLength={150} className={inputClass} value={config.platform_name} onChange={e=>setConfig({...config,platform_name:e.target.value})}/></Field><Field label="Support email"><input type="email" className={inputClass} value={config.support_email||""} onChange={e=>setConfig({...config,support_email:e.target.value})}/></Field><label className="flex items-start gap-3 rounded-xl border p-4"><input type="checkbox" className="mt-1" checked={config.allow_college_creation} onChange={e=>setConfig({...config,allow_college_creation:e.target.checked})}/><span><span className="block font-semibold">Allow new colleges</span><span className="app-caption mt-1 block text-sm">When disabled, existing colleges continue to operate, but new colleges cannot be created.</span></span></label><Button type="submit" loading={saving}>Save configuration</Button></form>}</>;
}
