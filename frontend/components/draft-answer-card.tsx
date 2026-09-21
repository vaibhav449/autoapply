"use client";

import { useState } from "react";
import { updateDraftAnswer } from "@/app/applications/actions";
import { AlertTriangleIcon, PencilIcon } from "@/components/icons";
import { SubmitButton } from "@/components/submit-button";
import type { DraftAnswerOut } from "@/lib/api";

/**
 * One drafted answer, readable by default and editable in place. Saving
 * re-runs the grounding check on the new wording, so the flags below always
 * describe the text that is actually there rather than the text it replaced.
 */
export function DraftAnswerCard({
  applicationId,
  answer,
  redirectTo,
}: {
  applicationId: number;
  answer: DraftAnswerOut;
  /** Where to land after saving — a queue passes its own path to stay put. */
  redirectTo?: string;
}) {
  const [editing, setEditing] = useState(false);
  const save = updateDraftAnswer.bind(null, applicationId, answer.id);

  return (
    <section className="card">
      <div className="card-head">
        <div className="card-head-text">
          <h3>{answer.question_text}</h3>
        </div>
        {!editing && (
          <button type="button" className="btn btn-secondary" onClick={() => setEditing(true)}>
            <PencilIcon width={15} height={15} />
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <form action={save}>
          <div className="field">
            <label htmlFor={`answer_${answer.id}`} className="sr-only">
              {answer.question_text}
            </label>
            <textarea
              id={`answer_${answer.id}`}
              name="answer_text"
              rows={6}
              defaultValue={answer.answer_text}
              required
            />
            <span className="field-hint">
              Saving re-checks this against your resume and projects, so the flags below match
              what you actually wrote.
            </span>
          </div>
          {redirectTo && <input type="hidden" name="redirect_to" value={redirectTo} />}
          <div className="button-row">
            <SubmitButton pendingLabel="Saving…">Save answer</SubmitButton>
            <button type="button" className="btn btn-secondary" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="document">{answer.answer_text}</div>
      )}

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
  );
}
