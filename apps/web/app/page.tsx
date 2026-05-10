import Link from "next/link";

const features = [
  {
    title: "Finds matching jobs daily",
    desc: "Rico scans job boards and surfaces roles that match your skills, salary range, location, and seniority — no manual searching.",
  },
  {
    title: "Scores and explains every match",
    desc: "Each job gets a fit score with reasons: title match, salary fit, skill overlap. You see why it ranked, not just that it did.",
  },
  {
    title: "Tracks your full pipeline",
    desc: "Applications, follow-ups, and outcomes in one place. Rico keeps your job search organised so nothing falls through the cracks.",
  },
];

const trust = [
  "UAE-focused search",
  "Profile-aware matching",
  "Human-approved applications",
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Nav */}
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <span className="text-sm font-bold tracking-wide text-white">Rico AI</span>
        <Link
          href="/login"
          className="text-sm text-zinc-400 transition-colors hover:text-white"
        >
          Sign in →
        </Link>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-4xl px-6 pb-20 pt-16 text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
          Now in early access
        </div>

        <h1 className="mb-6 text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl md:text-6xl lg:text-7xl">
          The AI that hunts jobs
          <br />
          <span className="text-indigo-400">while you live your life.</span>
        </h1>

        <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-zinc-400">
          Rico is an autonomous AI job-search agent. It finds roles that fit
          your profile, scores them, and helps you apply — so you can focus
          on the right opportunities.
        </p>

        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/login"
            className="w-full rounded-lg bg-indigo-600 px-8 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 sm:w-auto"
          >
            Start setup
          </Link>
          <Link
            href="/dashboard"
            className="w-full rounded-lg border border-zinc-700 px-8 py-3 text-sm font-semibold text-zinc-300 transition-colors hover:border-zinc-500 hover:text-white sm:w-auto"
          >
            View dashboard
          </Link>
        </div>
      </section>

      {/* Feature grid */}
      <section className="mx-auto max-w-5xl px-6 pb-10">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-6"
            >
              <h3 className="mb-2 text-sm font-semibold text-white">{f.title}</h3>
              <p className="text-sm leading-relaxed text-zinc-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust row */}
      <section className="mx-auto max-w-5xl px-6 pb-24">
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 pt-6">
          {trust.map((item) => (
            <span key={item} className="flex items-center gap-2 text-xs text-zinc-500">
              <span className="h-1 w-1 rounded-full bg-indigo-500" />
              {item}
            </span>
          ))}
        </div>
      </section>

      {/* Bottom CTA band */}
      <section className="border-t border-zinc-800 bg-zinc-900/30 px-6 py-16 text-center">
        <h2 className="mb-3 text-2xl font-bold text-white sm:text-3xl">
          Ready to let Rico work for you?
        </h2>
        <p className="mb-8 text-zinc-400">
          Set up your profile once. Rico handles the rest.
        </p>
        <Link
          href="/login"
          className="inline-block rounded-lg bg-indigo-600 px-8 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
        >
          Start your job search
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-800 px-6 py-6 text-center">
        <p className="text-xs text-zinc-600">© 2026 Rico AI — built for job seekers</p>
      </footer>
    </div>
  );
}
