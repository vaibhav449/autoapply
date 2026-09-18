import Link from "next/link";
import { BriefcaseIcon } from "@/components/icons";
import {
  APPLICATION_STATE_LABELS,
  apiGet,
  type ApplicationOut,
  type ApplicationState,
  type JobOut,
} from "@/lib/api";

const COLUMNS: ApplicationState[] = [
  "interested",
  "tailoring",
  "ready_for_review",
  "pending_captcha",
  "approved",
  "rejected_by_user",
  "submitted",
  "response_tracked",
];

type Row = { application: ApplicationOut; job: JobOut | null };

async function withJob(application: ApplicationOut): Promise<Row> {
  try {
    const job = await apiGet<JobOut>(`/api/v1/jobs/${application.job_id}`);
    return { application, job };
  } catch {
    // A job row could theoretically disappear; the card still needs to render.
    return { application, job: null };
  }
}

export default async function ApplicationsPage() {
  const applications = await apiGet<ApplicationOut[]>("/api/v1/applications/");
  const rows = await Promise.all(applications.map(withJob));

  const byState = new Map<ApplicationState, Row[]>(COLUMNS.map((state) => [state, []]));
  for (const row of rows) {
    byState.get(row.application.state)?.push(row);
  }

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
        {COLUMNS.map((state) => {
          const columnRows = byState.get(state) ?? [];
          return (
            <div key={state} className="kanban-column">
              <div className="kanban-column-head">
                <span>{APPLICATION_STATE_LABELS[state]}</span>
                <span className="kanban-count">{columnRows.length}</span>
              </div>
              {columnRows.length === 0 ? (
                <div className="kanban-placeholder">No applications here yet</div>
              ) : (
                columnRows.map(({ application, job }) => (
                  <Link
                    key={application.id}
                    href={`/applications/${application.id}`}
                    className="kanban-card"
                  >
                    <span className="kanban-card-title">{job?.title ?? "Untitled role"}</span>
                    <span className="kanban-card-meta">{job?.company ?? "Unknown company"}</span>
                  </Link>
                ))
              )}
            </div>
          );
        })}
      </div>

      {applications.length === 0 && (
        <div className="empty-panel">
          <span className="empty-panel-icon">
            <BriefcaseIcon width={22} height={22} />
          </span>
          <h2>Board is empty</h2>
          <p>
            Click &quot;Start application&quot; on a matched job from your profile to begin
            tracking it here.
          </p>
        </div>
      )}
    </main>
  );
}
