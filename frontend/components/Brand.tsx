import Link from "next/link";

export default function Brand({compact=false,href="/"}:{compact?:boolean;href?:string}){
  return <Link href={href} className="inline-flex items-center gap-3 rounded-lg">
    <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-600 font-bold text-white shadow-lg shadow-emerald-600/20">A</span>
    {!compact&&<span className="min-w-0"><span className="app-title block font-semibold leading-5">AntimBench</span><span className="app-caption block truncate text-xs">Attendance &amp; Student Support</span></span>}
  </Link>;
}
