import Link from "next/link";

export default function Home() {
  return <main className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-12">
    <section className="w-full max-w-3xl text-center">
      <p className="mb-5 text-sm font-semibold uppercase tracking-[0.28em] text-emerald-400">Techspire College</p>
      <h1 className="text-balance text-4xl font-bold leading-tight sm:text-6xl">Smart attendance and student support, in one place.</h1>
      <p className="mx-auto mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">AntimBench helps students and college teams manage attendance, schedules, and timely academic support.</p>
      <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
        <Link className="rounded-xl bg-emerald-400 px-7 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300" href="/login">Log In</Link>
        <Link className="rounded-xl border border-slate-700 px-7 py-3 font-semibold text-white transition hover:border-emerald-400 hover:text-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300" href="/signup">Sign Up</Link>
      </div>
    </section>
  </main>;
}
