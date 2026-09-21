import Link from "next/link";
import { transitionApplication } from "@/app/applications/actions";
import { DraftAnswerCard } from "@/components/draft-answer-card";
import { AlertTriangleIcon, ClipboardCheckIcon, ExternalLinkIcon } from "@/components/icons";
import { SubmitButton } from "@/components/submit-button";
import {
  APPLICATION_STATE_LABELS,
  apiGet,
  type ApplicationOut,
  type ApplicationState,
  type DraftAnswerOut,
  type JobOut,
  type ProfileOut,
} from "@/lib/api";

export default async function ReviewPage() {
  const waiting = await apiGet<ApplicationOut[]>(
    "/api/v1/applications/?state=ready_for_review",
  );

  if (waiting.length === 0) {
    return (
      <main>
        <div className="page-header-text">
          <h1>Review</h1>
          <p>
            One application at a time — what was filled and what was drafted, checked before
            anything is approved.
          </p>
        </div>

        <div className="empty-panel">
          <span className="empty-panel-icon">
            <ClipboardCheckIcon width={22} height={22} />
          </span>
          <h2>Nothing ready for review</h2>
          <p>
            Applications land here once tailoring finishes for them. Approve to submit, or send
            them to the pending queue if they hit a CAPTCHA or login wall.
          </p>
        </div>
      </main>
    );
  }

  // Oldest first, one at a time: acting on this one drops it out of the queue
  // and the next takes its place, so there is no position to keep track of.
  const application = waiting[waiting.length - 1];
  const [profile, job, draftAnswers] = await Promise.all([
    apiGet<ProfileOut>(`/api/v1/profiles/${application.profile_id}`),
    apiGet<JobOut>(`/api/v1/jobs/${application.job_id}`),
    apiGet<DraftAnswerOut[]>(`/api/v1/applications/${application.id}/draft-answers`),
  ]);

  const flagged = draftAnswers.filter((answer) => answer.unverified_claims.length > 0).length;

  return (
    <main>
      <div className="page-header-text">
        <h1>Review</h1>
        <p>
          One application at a time — what was filled and what was drafted, checked before
          anything is approved.
          {waiting.length > 1 ? ` ${waiting.length - 1} more waiting after this one.` : ""}
        </p>
      </div>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>{job.title}</h2>
            <p className="text-muted text-small">
              {job.company}
              {job.location ? ` · ${job.location}` : ""} · for{" "}
              <Link href={`/profiles/${profile.id}`}>{profile.name}</Link>
            </p>
          </div>
          <a href={job.url} target="_blank" rel="noreferrer" className="btn btn-secondary">
            <ExternalLinkIcon width={16} height={16} />
            Open posting
          </a>
        </div>

        <div className="button-row">
          <Link href={`/applications/${application.id}`} className="btn btn-secondary">
            Full application
          </Link>
          {application.cover_letter_id && (
            <Link
              href={`/profiles/${profile.id}/jobs/${job.id}/cover-letter`}
              className="btn btn-secondary"
            >
              Cover letter
            </Link>
          )}
          {application.resume_variant_id && (
            <Link href={`/profiles/${profile.id}/resumes`} className="btn btn-secondary">
              Resume variant
            </Link>
          )}
        </div>

        {flagged > 0 && (
          <div className="alert alert-warning">
            <AlertTriangleIcon className="alert-icon" width={18} height={18} />
            <div className="alert-body">
              <strong>
                {flagged} of {draftAnswers.length} answers have claims that couldn&apos;t be
                verified
              </strong>
              <p>
                Each one is flagged below. They aren&apos;t necessarily wrong — the check is
                deliberately strict — but they are the lines worth reading before approving.
              </p>
            </div>
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Draft answers</h2>
        </div>
        {draftAnswers.length === 0 ? (
          <p className="empty-state">
            No answers drafted yet — they&apos;re generated when a form is filled, or one at a
            time from the full application page.
          </p>
        ) : (
          draftAnswers.map((answer) => (
            <DraftAnswerCard
              key={answer.id}
              applicationId={application.id}
              answer={answer}
              redirectTo="/review"
            />
          ))
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Decision</h2>
            <p className="text-muted text-small">
              Approving records your sign-off — it does not submit anything. Submission stays a
              step you take on the posting itself.
            </p>
          </div>
        </div>
        <div className="button-row">
          {application.legal_next_states.map((state: ApplicationState) => (
            <form key={state} action={transitionApplication.bind(null, application.id)}>
              <input type="hidden" name="target_state" value={state} />
              <input type="hidden" name="redirect_to" value="/review" />
              <SubmitButton
                pendingLabel="Saving…"
                variant={state === "approved" ? "primary" : "secondary"}
              >
                {APPLICATION_STATE_LABELS[state]}
              </SubmitButton>
            </form>
          ))}
        </div>
      </section>
    </main>
  );
}
