import Link from "next/link";
import { transitionApplication, createDraftAnswer } from "@/app/applications/actions";
import { FillFormPanel } from "@/components/fill-form-panel";
import { SubmitButton } from "@/components/submit-button";
import { AlertTriangleIcon, ArrowLeftIcon, ExternalLinkIcon } from "@/components/icons";
import {
  APPLICATION_STATE_LABELS,
  apiGet,
  type ApplicationOut,
  type DraftAnswerOut,
  type JobOut,
  type ProfileOut,
} from "@/lib/api";

export default async function ApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const applicationId = Number(id);

  const application = await apiGet<ApplicationOut>(`/api/v1/applications/${id}`);
  const [profile, job, draftAnswers] = await Promise.all([
    apiGet<ProfileOut>(`/api/v1/profiles/${application.profile_id}`),
    apiGet<JobOut>(`/api/v1/jobs/${application.job_id}`),
    apiGet<DraftAnswerOut[]>(`/api/v1/applications/${id}/draft-answers`),
  ]);

  const transitionWithId = transitionApplication.bind(null, applicationId);
  const createAnswerWithId = createDraftAnswer.bind(null, applicationId);

  return (
    <main>
      <Link href="/applications" className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        All applications
      </Link>

      <div className="page-header">
        <div className="page-header-text">
          <span className={`state-badge state-${application.state}`}>
            {APPLICATION_STATE_LABELS[application.state]}
          </span>
          <h1>{job.title}</h1>
          <p>
            {job.company}
            {job.location ? ` · ${job.location}` : ""} · for{" "}
            <Link href={`/profiles/${profile.id}`}>{profile.name}</Link>
          </p>
        </div>
        <div className="page-header-actions">
          <a href={job.url} target="_blank" rel="noreferrer" className="btn btn-secondary">
            <ExternalLinkIcon width={16} height={16} />
            View posting
          </a>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Move this application</h2>
          </div>
        </div>
        {application.legal_next_states.length === 0 ? (
          <p className="text-muted text-small">
            This is a terminal state — nothing to move it to.
          </p>
        ) : (
          <div className="button-row">
            {application.legal_next_states.map((state) => (
              <form key={state} action={transitionWithId}>
                <input type="hidden" name="target_state" value={state} />
                <SubmitButton pendingLabel="Moving…">
                  Mark {APPLICATION_STATE_LABELS[state]}
                </SubmitButton>
              </form>
            ))}
          </div>
        )}
        {application.cover_letter_id && (
          <p className="text-muted text-small">
            <Link href={`/profiles/${profile.id}/jobs/${job.id}/cover-letter`}>
              View generated cover letter →
            </Link>
          </p>
        )}
        {application.resume_variant_id && (
          <p className="text-muted text-small">
            <Link href={`/profiles/${profile.id}/resumes`}>View resume variants →</Link>
          </p>
        )}
      </section>

      <FillFormPanel applicationId={application.id} />

      <section className="section">
        <div className="section-head">
          <h2>Draft answers</h2>
        </div>
        <p className="text-muted text-small">
          Grounded in {profile.name}&apos;s real resume and project content — anything the
          model couldn&apos;t verify against that source is flagged below, not silently
          submitted.
        </p>

        <section className="card">
          <form action={createAnswerWithId}>
            <div className="field">
              <label htmlFor="question_text">Application question</label>
              <textarea
                id="question_text"
                name="question_text"
                rows={2}
                placeholder="e.g. Why do you want to work here?"
                required
              />
            </div>
            <div className="form-footer">
              <SubmitButton pendingLabel="Generating…">Generate answer</SubmitButton>
            </div>
          </form>
        </section>

        {draftAnswers.length === 0 ? (
          <p className="empty-state">No draft answers yet.</p>
        ) : (
          draftAnswers.map((answer) => (
            <section key={answer.id} className="card">
              <div className="card-head">
                <div className="card-head-text">
                  <h3>{answer.question_text}</h3>
                </div>
              </div>
              <div className="document">{answer.answer_text}</div>
              {answer.unverified_claims.length > 0 && (
                <div className="alert alert-warning">
                  <AlertTriangleIcon className="alert-icon" width={18} height={18} />
                  <div className="alert-body">
                    <strong>Unverified — not found in the source resume/projects</strong>
                    <ul>
                      {answer.unverified_claims.map((claim) => (
                        <li key={claim}>{claim}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </section>
          ))
        )}
      </section>
    </main>
  );
}
