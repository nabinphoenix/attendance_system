import Link from "next/link";
export default function RoleShell({ role, children }: { role: string; children: React.ReactNode }) {
  return <div className="min-h-screen"><header className="border-b border-slate-800 px-6 py-4"><Link href="/" className="font-bold text-emerald-400">AntimBench</Link><span className="ml-3 text-sm capitalize text-slate-400">{role} workspace</span></header><main className="p-6">{children}</main></div>;
}
