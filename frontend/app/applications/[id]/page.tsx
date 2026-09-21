import Link from "next/link";
import {
  transitionApplication,
  createDraftAnswer,
  recordOutcome,
} from "@/app/applications/actions";
import { DraftAnswerCard } from "@/components/draft-answer-card";
import { FillFormPanel } from "@/components/fill-form-panel";
import { SubmitButton } from "@/components/submit-button";
import { ArrowLeftIcon, ExternalLinkIcon } from "@/components/icons";
import {
  APPLICATION_STATE_LABELS,
  OUTCOME_KIND_LABELS,
  apiGet,
  type ApplicationOut,
  type ApplicationOutcomeOut,
  type DraftAnswerOut,
  type OutcomeKind,
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
  const [profile, job, draftAnswers, outcomes] = await Promise.all([
    apiGet<ProfileOut>(`/api/v1/profiles/${application.profile_id}`),
    apiGet<JobOut>(`/api/v1/jobs/${application.job_id}`),
    apiGet<DraftAnswerOut[]>(`/api/v1/applications/${id}/draft-answers`),
    apiGet<ApplicationOutcomeOut[]>(`/api/v1/applications/${id}/outcomes`),
  ]);

  const transitionWithId = transitionApplication.bind(null, applicationId);
  const createAnswerWithId = createDraftAnswer.bind(null, applicationId);
  const recordOutcomeWithId = recordOutcome.bind(null, applicationId);
  // Only offered once something has actually gone out — "rejected" on an
  // application nobody sent is not a fact worth recording.
  const canRecordOutcome = Boolean(application.submitted_at);

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

      {(canRecordOutcome || outcomes.length > 0) && (
        <section className="card">
          <div className="card-head">
            <div className="card-head-text">
              <h2>What came back</h2>
              <p className="text-muted text-small">
                Every response is kept, not just the most recent — an application that
                reached an interview still counts as one after a later rejection.
              </p>
            </div>
          </div>

          {outcomes.length === 0 ? (
            <p className="text-muted text-small">Nothing recorded yet.</p>
          ) : (
            <ul className="fill-field-list">
              {outcomes.map((outcome) => (
                <li key={outcome.id}>
                  <span className="fill-field-name">
                    {OUTCOME_KIND_LABELS[outcome.kind]} ·{" "}
                    {new Date(outcome.occurred_at).toLocaleDateString()}
                  </span>
                  {outcome.note && <span className="fill-field-value">{outcome.note}</span>}
                </li>
              ))}
            </ul>
          )}

          {canRecordOutcome && (
            <form action={recordOutcomeWithId}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="kind">Record a response</label>
                  <select id="kind" name="kind" required>
                    {(Object.keys(OUTCOME_KIND_LABELS) as OutcomeKind[]).map((kind) => (
                      <option key={kind} value={kind}>
                        {OUTCOME_KIND_LABELS[kind]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="note">Note (optional)</label>
                  <input id="note" name="note" type="text" placeholder="e.g. 30 min with the hiring manager" />
                </div>
              </div>
              <div className="form-footer">
                <SubmitButton pendingLabel="Recording…">Record</SubmitButton>
              </div>
            </form>
          )}
        </section>
      )}

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
            <DraftAnswerCard key={answer.id} applicationId={applicationId} answer={answer} />
          ))
        )}
      </section>
    </main>
  );
}
