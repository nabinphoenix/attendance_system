import Link from "next/link";
import Image from "next/image";
import { type MouseEventHandler } from "react";

export default function Brand({compact=false,href="/",onClick}:{compact?:boolean;href?:string;onClick?:MouseEventHandler<HTMLAnchorElement>}){
  return <Link href={href} onClick={onClick} aria-label="AntimBench" className="inline-flex items-center gap-3 rounded-lg">
    <Image src="/logo.png" alt="" aria-hidden="true" width={48} height={48} priority className="h-9 w-9 shrink-0 object-contain" />
    {!compact&&<span className="min-w-0"><span className="app-title block font-semibold leading-5">AntimBench</span><span className="app-caption block truncate text-xs">Attendance &amp; Student Support</span></span>}
  </Link>;
}
