import { ClipboardCheckIcon } from "@/components/icons";

export default function ReviewPage() {
  return (
    <main>
      <div className="page-header-text">
        <h1>Review</h1>
        <p>One application at a time — filled fields and draft answers, editable, single approve action.</p>
      </div>

      <div className="empty-panel">
        <span className="empty-panel-icon">
          <ClipboardCheckIcon width={22} height={22} />
        </span>
        <h2>Nothing ready for review</h2>
        <p>
          Applications land here once tailoring finishes for them. Approve to submit, or send them
          to the pending queue if they hit a CAPTCHA or login wall.
        </p>
      </div>
    </main>
  );
}
