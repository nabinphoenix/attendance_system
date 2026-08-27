import type { ButtonHTMLAttributes } from "react";
type Variant="primary"|"secondary"|"outline"|"danger"|"ghost";
type Size="sm"|"md"|"lg"|"icon";
type Props=ButtonHTMLAttributes<HTMLButtonElement>&{variant?:Variant;size?:Size;loading?:boolean};
const variants:Record<Variant,string>={
  primary:"border border-emerald-400 bg-emerald-400 text-slate-950 hover:border-emerald-300 hover:bg-emerald-300",
  secondary:"border border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700",
  outline:"border border-slate-700 bg-transparent text-slate-200 hover:border-slate-500 hover:bg-slate-800/60",
  danger:"border border-red-500/50 bg-red-500/15 text-red-300 hover:bg-red-500/25",
  ghost:"border border-transparent bg-transparent text-slate-300 hover:bg-slate-800 hover:text-white",
};
const sizes:Record<Size,string>={sm:"min-h-8 px-3 py-1.5 text-xs",md:"min-h-10 px-4 py-2 text-sm",lg:"min-h-12 px-5 py-3",icon:"h-10 w-10 p-0"};
export function Button({variant="primary",size="md",loading=false,disabled,className="",children,...props}:Props){return <button {...props} disabled={disabled||loading} aria-busy={loading||undefined} className={`inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${sizes[size]} ${className}`}>{loading&&<span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"/>}{children}</button>}
