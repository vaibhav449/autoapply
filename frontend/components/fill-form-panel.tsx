"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { fillApplicationForm } from "@/app/applications/actions";
import { AlertTriangleIcon, CheckCircleIcon } from "@/components/icons";
import { fillScreenshotUrl, type FillAttemptOut } from "@/lib/api";

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function FillFormPanel({
  applicationId,
  attempts,
}: {
  applicationId: number;
  /** Every past run, newest first — server-rendered, so a reviewer who goes
   * off to the live posting and comes back still has the list of what was
   * skipped in front of them. */
  attempts: FillAttemptOut[];
}) {
  const router = useRouter();
  const [justRan, setJustRan] = useState<FillAttemptOut | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // router.refresh() below brings the new attempt down in `attempts` too, a
  // moment after it is already in `justRan` — merging on id keeps it from
  // being shown twice during that gap.
  const all = useMemo(() => {
    if (justRan === null || attempts.some((attempt) => attempt.id === justRan.id)) {
      return attempts;
    }
    return [justRan, ...attempts];
  }, [attempts, justRan]);

  const latest = all[0] ?? null;
  const earlier = all.slice(1);

  async function handleRun() {
    setPending(true);
    setError(null);
    try {
      setJustRan(await fillApplicationForm(applicationId));
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
          {pending ? "Filling…" : latest ? "Fill again" : "Fill form"}
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

      {latest && (
        <div className="fill-result">
          {latest.status === "captcha_required" && (
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

          {latest.status === "form_not_found" && (
            <div className="alert alert-danger">
              <AlertTriangleIcon className="alert-icon" width={18} height={18} />
              <div className="alert-body">
                <strong>Couldn&apos;t find the application form</strong>
                <p>The posting may have moved, or this site isn&apos;t supported yet.</p>
              </div>
            </div>
          )}

          {latest.status === "filled" && (
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

          <p className="text-muted text-small">
            {/* Rendered from the browser's own timezone, which the server has no
                way to know — the mismatch is expected here, not a bug to chase. */}
            <time dateTime={latest.created_at} suppressHydrationWarning>
              {new Date(latest.created_at).toLocaleString()}
            </time>{" "}
            · took {formatDuration(latest.duration_ms)}
          </p>

          {latest.has_screenshot && (
            // eslint-disable-next-line @next/next/no-img-element -- served by the API, not a bundled asset
            <img
              src={fillScreenshotUrl(applicationId, latest.id)}
              alt="Screenshot of the filled application form"
              className="fill-result-screenshot"
            />
          )}

          <div className="fill-result-columns">
            <div>
              <h3>Filled ({Object.keys(latest.filled_fields).length})</h3>
              {Object.keys(latest.filled_fields).length === 0 ? (
                <p className="text-muted text-small">Nothing was filled.</p>
              ) : (
                <ul className="fill-field-list">
                  {Object.entries(latest.filled_fields).map(([field, value]) => (
                    <li key={field}>
                      <span className="fill-field-name">{field}</span>
                      <span className="fill-field-value">{value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3>Skipped ({latest.skipped_fields.length})</h3>
              {latest.skipped_fields.length === 0 ? (
                <p className="text-muted text-small">Nothing was skipped.</p>
              ) : (
                <ul className="fill-field-list">
                  {latest.skipped_fields.map((field) => (
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

      {earlier.length > 0 && (
        <details className="fill-history">
          <summary>
            {earlier.length} earlier {earlier.length === 1 ? "run" : "runs"}
          </summary>
          <ul className="fill-field-list">
            {earlier.map((attempt) => (
              <li key={attempt.id}>
                <span className="fill-field-name">
                  <time dateTime={attempt.created_at} suppressHydrationWarning>
                    {new Date(attempt.created_at).toLocaleString()}
                  </time>
                </span>
                <span className="fill-field-value">
                  {Object.keys(attempt.filled_fields).length} filled ·{" "}
                  {attempt.skipped_fields.length} skipped
                  {attempt.status !== "filled" && ` · ${attempt.status.replace("_", " ")}`}
                  {attempt.has_screenshot && (
                    <>
                      {" · "}
                      <a
                        href={fillScreenshotUrl(applicationId, attempt.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        screenshot
                      </a>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
