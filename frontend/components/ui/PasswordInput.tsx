"use client";
import { InputHTMLAttributes, useState } from "react";

type Props=Omit<InputHTMLAttributes<HTMLInputElement>,"type">;
export function PasswordInput({className="",...props}:Props){
  const[visible,setVisible]=useState(false);
  return <div className="relative"><input {...props} type={visible?"text":"password"} className={`${className} pr-12`}/><button type="button" onClick={()=>setVisible(value=>!value)} aria-label={visible?"Hide password":"Show password"} className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-slate-400 hover:text-emerald-300 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-400">
    {visible?<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="h-5 w-5"><path strokeLinecap="round" strokeWidth="1.8" d="M3 3l18 18M10.6 10.7a2 2 0 002.7 2.7M9.9 4.2A10.8 10.8 0 0112 4c5 0 8.5 4.2 9.5 6a2 2 0 010 2 16 16 0 01-3 3.7M6.2 6.2A16 16 0 002.5 10a2 2 0 000 2c1 1.8 4.5 6 9.5 6 1 0 2-.2 2.8-.5"/></svg>:<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="h-5 w-5"><path strokeLinecap="round" strokeWidth="1.8" d="M2.5 10a2 2 0 000 2c1 1.8 4.5 6 9.5 6s8.5-4.2 9.5-6a2 2 0 000-2C20.5 8.2 17 4 12 4S3.5 8.2 2.5 10z"/><circle cx="12" cy="11" r="3"/></svg>}
  </button></div>;
}
