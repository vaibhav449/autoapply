import Link from "next/link";
import { transitionApplication } from "@/app/applications/actions";
import { ClockIcon, ExternalLinkIcon } from "@/components/icons";
import { SubmitButton } from "@/components/submit-button";
import {
  apiGet,
  type ApplicationOut,
  type JobOut,
  type ProfileOut,
} from "@/lib/api";

type Row = { application: ApplicationOut; job: JobOut | null; profile: ProfileOut | null };

async function withContext(application: ApplicationOut): Promise<Row> {
  // Settled, not all: one missing row should cost that card its title, not the
  // whole queue. A stuck application is the last thing to hide behind an error.
  const [job, profile] = await Promise.all([
    apiGet<JobOut>(`/api/v1/jobs/${application.job_id}`).catch(() => null),
    apiGet<ProfileOut>(`/api/v1/profiles/${application.profile_id}`).catch(() => null),
  ]);
  return { application, job, profile };
}

export default async function PendingPage() {
  const applications = await apiGet<ApplicationOut[]>(
    "/api/v1/applications/?state=pending_captcha",
  );
  const rows = await Promise.all(applications.map(withContext));

  return (
    <main>
      <div className="page-header-text">
        <h1>Pending</h1>
        <p>
          Applications blocked by a CAPTCHA or login wall — flagged for you to finish by hand,
          never bypassed.
        </p>
      </div>

      {rows.length === 0 ? (
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
      ) : (
        rows.map(({ application, job, profile }) => (
          <section key={application.id} className="card">
            <div className="card-head">
              <div className="card-head-text">
                <h2>{job?.title ?? "Untitled role"}</h2>
                <p className="text-muted text-small">
                  {job?.company ?? "Unknown company"}
                  {job?.location ? ` · ${job.location}` : ""}
                  {profile ? ` · for ${profile.name}` : ""}
                </p>
              </div>
              {job && (
                <a href={job.url} target="_blank" rel="noreferrer" className="btn btn-secondary">
                  <ExternalLinkIcon width={16} height={16} />
                  Open posting
                </a>
              )}
            </div>

            <p className="text-muted text-small">
              The form was filled and left unsubmitted. Solve the CAPTCHA on the posting, check
              the answers against what&apos;s drafted, and submit it yourself — then mark it
              submitted here so it leaves this queue.
            </p>

            <div className="button-row">
              <Link href={`/applications/${application.id}`} className="btn btn-secondary">
                Review answers
              </Link>
              {application.legal_next_states.includes("submitted") && (
                <form action={transitionApplication.bind(null, application.id)}>
                  <input type="hidden" name="target_state" value="submitted" />
                  <input type="hidden" name="redirect_to" value="/pending" />
                  <SubmitButton pendingLabel="Marking…">Mark submitted</SubmitButton>
                </form>
              )}
            </div>
          </section>
        ))
      )}
    </main>
  );
}
