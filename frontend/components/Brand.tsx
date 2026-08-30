import Link from "next/link";
import { type MouseEventHandler } from "react";

export default function Brand({compact=false,href="/",onClick}:{compact?:boolean;href?:string;onClick?:MouseEventHandler<HTMLAnchorElement>}){
  return <Link href={href} onClick={onClick} aria-label="AntimBench" className="inline-flex items-center gap-3 rounded-lg">
    <svg aria-hidden="true" focusable="false" viewBox="0 0 245 168" className="h-9 w-[3.25rem] shrink-0" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M44.6806 91.3484L67.1806 123.848L53.1806 156.348L14.1806 156.348L44.6806 91.3484Z" fill="#005CDE" />
      <path d="M166 98.9026L140.174 124.848L153.5 157.348L193.174 157.348L166 98.9026Z" fill="#005CDE" />
      <path d="M84.4999 5.90249L122 5.90249L146.5 65.4026L119.5 85.4026L102.5 43.9026L84.4999 86.9026L57 69.7704L84.4999 5.90249Z" fill="#005ADD" />
      <path d="M180.188 73.1094L180.162 73.1299L180.14 73.1533L100.561 155.716L38.4229 67.3652L102.548 109.573L102.853 109.773L103.137 109.546L170.403 55.459L241.681 24.0098L180.188 73.1094Z" fill="#01B101" stroke="#747474" />
    </svg>
    {!compact&&<span className="min-w-0"><span className="app-title block font-semibold leading-5">AntimBench</span><span className="app-caption block truncate text-xs">Attendance &amp; Student Support</span></span>}
  </Link>;
}
