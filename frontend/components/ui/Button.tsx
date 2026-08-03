import type { ButtonHTMLAttributes } from "react";
export function Button(props: ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...props} className={`rounded-lg bg-emerald-400 px-4 py-2 font-semibold text-slate-950 ${props.className ?? ""}`} />; }
