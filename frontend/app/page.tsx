import Link from "next/link";
import { BarChartIcon, ClipboardCheckIcon, SparklesIcon } from "@/components/icons";

const PIPELINE_STAGES = [
  {
    icon: SparklesIcon,
    title: "Discover & score",
    body: "Postings are pulled from ATS boards and aggregators, then ranked against your profile — qualified, stretch, or excluded, with the reasoning shown.",
  },
  {
    icon: ClipboardCheckIcon,
    title: "Tailor per role",
    body: "Resume variants and cover letters are generated from your real experience only — anything the model can't verify is flagged, never invented.",
  },
  {
    icon: BarChartIcon,
    title: "Review & track",
    body: "Nothing submits unattended. Every application is a single approve-and-go screen, with outcomes tracked back to the variant that produced them.",
  },
];

export default function Home() {
  return (
    <main>
      <section className="hero-panel">
        <span className="eyebrow">Personal application pipeline</span>
        <h1>Build your profile once. Let the pipeline find and tailor the rest.</h1>
        <p>
          AutoApply discovers postings that match your skills, ranks them against your real
          experience, and drafts a tailored resume and cover letter for each one — you stay in
          control of every submission.
        </p>
        <div className="hero-panel-actions">
          <Link href="/profiles/new" className="btn btn-primary">
            Create your profile
          </Link>
          <Link href="/profiles" className="btn btn-secondary">
            View profiles
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>How it works</h2>
        </div>
        <div className="feature-grid">
          {PIPELINE_STAGES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="feature-card">
              <span className="feature-card-icon">
                <Icon />
              </span>
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
