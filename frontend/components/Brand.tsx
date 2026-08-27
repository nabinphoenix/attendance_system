import Link from "next/link";

export default function Brand({compact=false,href="/"}:{compact?:boolean;href?:string}){
  return <Link href={href} className="inline-flex items-center gap-3 rounded-lg focus-visible:ring-offset-slate-900">
    <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-400 font-bold text-slate-950">A</span>
    {!compact&&<span className="min-w-0"><span className="block font-semibold leading-5 text-white">AntimBench</span><span className="block truncate text-xs text-slate-400">Attendance &amp; Student Support</span></span>}
  </Link>;
}
