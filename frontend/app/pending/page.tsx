import { ClockIcon } from "@/components/icons";

export default function PendingPage() {
  return (
    <main>
      <div className="page-header-text">
        <h1>Pending</h1>
        <p>Applications blocked by a CAPTCHA or login wall — flagged for you to finish by hand, never bypassed.</p>
      </div>

      <div className="empty-panel">
        <span className="empty-panel-icon">
          <ClockIcon width={22} height={22} />
        </span>
        <h2>Nothing pending</h2>
        <p>
          When automation can&apos;t clear a form on its own, it lands here with full context on
          why — not silently dropped.
        </p>
      </div>
    </main>
  );
}
