import { BarChartIcon, BriefcaseIcon, ClipboardCheckIcon, ClockIcon } from "@/components/icons";

const STATS = [
  { icon: BriefcaseIcon, label: "Applications submitted", hint: "Total across all profiles" },
  { icon: ClipboardCheckIcon, label: "Response rate", hint: "Replies ÷ applications submitted" },
  { icon: ClockIcon, label: "Avg. time saved", hint: "Vs. manual form-filling" },
  { icon: BarChartIcon, label: "Best resume variant", hint: "By reply rate, once tracked" },
];

export default function AnalyticsPage() {
  return (
    <main>
      <div className="page-header-text">
        <h1>Analytics</h1>
        <p>Funnel, resume-variant response rate, and cost/latency — populates once applications start moving through the pipeline.</p>
      </div>

      <div className="stat-grid">
        {STATS.map(({ icon: Icon, label, hint }) => (
          <div key={label} className="stat-card">
            <span className="stat-card-icon">
              <Icon width={18} height={18} />
            </span>
            <span className="stat-card-value is-placeholder">—</span>
            <span className="stat-card-label">{label}</span>
            <span className="stat-card-hint">{hint}</span>
          </div>
        ))}
      </div>
    </main>
  );
}
