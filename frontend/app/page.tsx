import Link from "next/link";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";

const features = [
  { icon: "◌", title: "Attendance without friction", copy: "Check in with a secure, time-bound QR flow and see the result immediately." },
  { icon: "▦", title: "One clear academic view", copy: "Keep routines, rooms, classes and attendance in a single calm workspace." },
  { icon: "↗", title: "Support before it is urgent", copy: "Turn attendance patterns into timely follow-up for every student." },
];

export default function Home() {
  return <main className="landing">
    <nav className="landing-nav" aria-label="Main navigation">
      <Brand />
      <div className="landing-nav-actions">
        <ThemeToggle />
        <Link className="landing-login" href="/login">Log in</Link>
      </div>
    </nav>

    <section className="landing-hero">
      <div className="landing-hero-copy">
        <p className="landing-eyebrow">ATTENDANCE, WITH CONTEXT</p>
        <h1 className="landing-heading">More present students. <em>Less busywork.</em></h1>
        <p className="landing-lede">AntimBench gives students, teachers, and college teams one thoughtful place to manage attendance, routines, and early academic support.</p>
        <div className="landing-cta">
          <Link className="landing-primary" href="/login">Open your workspace <span aria-hidden="true">→</span></Link>
          <span className="landing-secondary">Account access by administrator</span>
        </div>
        <div className="landing-trust" aria-label="Key benefits"><span>Role-based access</span><span>Mobile-ready check-in</span><span>Built for college teams</span></div>
      </div>

      <div className="landing-preview" aria-label="AntimBench dashboard preview">
        <div className="landing-preview-bar"><span className="landing-preview-dots"><i /><i /><i /></span><span className="landing-preview-name">YOUR WEEK AT A GLANCE</span></div>
        <div className="landing-preview-inner">
          <div className="landing-preview-top"><p>Thursday, 27 August</p><h2>Good morning, Alex</h2></div>
          <div className="landing-preview-grid">
            <div className="landing-preview-card"><p>ATTENDANCE RATE</p><strong>82%</strong><div className="landing-progress"><i /></div></div>
            <div className="landing-preview-card"><p>CLASSES TODAY</p><strong>03</strong><div className="landing-progress"><i style={{ width: "58%" }} /></div></div>
            <div className="landing-classes">
              <div className="landing-class"><span>10:00 · Data Structures</span><b>Next up</b></div>
              <div className="landing-class"><span>13:00 · Web Technology</span><span>Room B204</span></div>
              <div className="landing-class"><span>15:00 · Project Lab</span><span>Lab 03</span></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section className="landing-stats" aria-label="Platform highlights">
      <div className="landing-stat"><strong>One workspace</strong><span>For students, teachers and staff</span></div>
      <div className="landing-stat"><strong>QR + location</strong><span>Attendance made more reliable</span></div>
      <div className="landing-stat"><strong>Early insight</strong><span>Support students when it matters</span></div>
    </section>

    <section className="landing-features">
      <p className="landing-section-kicker">DESIGNED FOR THE DAY-TO-DAY</p>
      <h2 className="landing-section-title">Everything important, without making the work feel heavier.</h2>
      <div className="landing-feature-grid">
        {features.map((feature) => <article className="landing-feature" key={feature.title}><span className="landing-feature-icon" aria-hidden="true">{feature.icon}</span><h3>{feature.title}</h3><p>{feature.copy}</p></article>)}
      </div>
    </section>
  </main>;
}
