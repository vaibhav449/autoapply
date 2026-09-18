"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { fillApplicationForm } from "@/app/applications/actions";
import { AlertTriangleIcon, CheckCircleIcon } from "@/components/icons";
import type { FillFormResultOut } from "@/lib/api";

export function FillFormPanel({ applicationId }: { applicationId: number }) {
  const router = useRouter();
  const [result, setResult] = useState<FillFormResultOut | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setPending(true);
    setError(null);
    try {
      setResult(await fillApplicationForm(applicationId));
      // A fill answers the form's own questions along the way, so the draft
      // answers below are stale the moment it finishes — without this they
      // keep reading "No draft answers yet" until a manual reload.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Filling the form failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div className="card-head-text">
          <h2>Fill the real application form</h2>
          <p className="text-muted text-small">
            Opens the live posting in a headless browser and fills in your name, contact info,
            resume, and every custom question it can safely answer — this never clicks submit.
            Review everything below, especially what it had to skip, before applying yourself.
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={pending} onClick={handleRun}>
          {pending ? "Filling…" : "Fill form"}
        </button>
      </div>

      {error && (
        <div className="alert alert-danger">
          <AlertTriangleIcon className="alert-icon" width={18} height={18} />
          <div className="alert-body">
            <strong>Couldn&apos;t fill this form</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {result && (
        <div className="fill-result">
          {result.status === "captcha_required" && (
            <div className="alert alert-warning">
              <AlertTriangleIcon className="alert-icon" width={18} height={18} />
              <div className="alert-body">
                <strong>CAPTCHA required</strong>
                <p>
                  Everything below was filled in, but the site is asking for a CAPTCHA. Open the
                  posting, solve it, and submit by hand once you&apos;ve reviewed the answers.
                </p>
              </div>
            </div>
          )}

          {result.status === "form_not_found" && (
            <div className="alert alert-danger">
              <AlertTriangleIcon className="alert-icon" width={18} height={18} />
              <div className="alert-body">
                <strong>Couldn&apos;t find the application form</strong>
                <p>The posting may have moved, or this site isn&apos;t supported yet.</p>
              </div>
            </div>
          )}

          {result.status === "filled" && (
            <div className="alert alert-info">
              <CheckCircleIcon className="alert-icon" width={18} height={18} />
              <div className="alert-body">
                <strong>Form filled — nothing submitted</strong>
                <p>
                  Review every field below, especially anything skipped, before applying by hand.
                </p>
              </div>
            </div>
          )}

          {result.screenshot_base64 && (
            // eslint-disable-next-line @next/next/no-img-element -- one-shot base64 result, not a served asset
            <img
              src={`data:image/png;base64,${result.screenshot_base64}`}
              alt="Screenshot of the filled application form"
              className="fill-result-screenshot"
            />
          )}

          <div className="fill-result-columns">
            <div>
              <h3>Filled ({Object.keys(result.filled_fields).length})</h3>
              {Object.keys(result.filled_fields).length === 0 ? (
                <p className="text-muted text-small">Nothing was filled.</p>
              ) : (
                <ul className="fill-field-list">
                  {Object.entries(result.filled_fields).map(([field, value]) => (
                    <li key={field}>
                      <span className="fill-field-name">{field}</span>
                      <span className="fill-field-value">{value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3>Skipped ({result.skipped_fields.length})</h3>
              {result.skipped_fields.length === 0 ? (
                <p className="text-muted text-small">Nothing was skipped.</p>
              ) : (
                <ul className="fill-field-list">
                  {result.skipped_fields.map((field) => (
                    <li key={field}>
                      <span className="fill-field-name">{field}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
