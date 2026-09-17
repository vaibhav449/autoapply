import { BriefcaseIcon } from "@/components/icons";

const COLUMNS = [
  { key: "interested", label: "Interested" },
  { key: "tailoring", label: "Tailoring" },
  { key: "ready_for_review", label: "Ready for review" },
  { key: "submitted", label: "Submitted" },
  { key: "response_tracked", label: "Response tracked" },
];

export default function ApplicationsPage() {
  return (
    <main>
      <div className="page-header-text">
        <h1>Applications</h1>
        <p>
          Every application you start moves through this pipeline as one row — from first
          interest through tailoring, review, submission, and tracked outcome.
        </p>
      </div>

      <div className="kanban">
        {COLUMNS.map((column) => (
          <div key={column.key} className="kanban-column">
            <div className="kanban-column-head">
              <span>{column.label}</span>
              <span className="kanban-count">0</span>
            </div>
            <div className="kanban-placeholder">No applications here yet</div>
          </div>
        ))}
      </div>

      <div className="empty-panel">
        <span className="empty-panel-icon">
          <BriefcaseIcon width={22} height={22} />
        </span>
        <h2>Board is empty</h2>
        <p>
          Click &quot;Start application&quot; on a matched job from your profile to begin tracking
          it here.
        </p>
      </div>
    </main>
  );
}
