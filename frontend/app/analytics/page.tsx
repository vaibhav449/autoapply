import { BarChartIcon, BriefcaseIcon, ClipboardCheckIcon, InboxIcon } from "@/components/icons";
import {
  APPLICATION_STATE_LABELS,
  OUTCOME_KIND_LABELS,
  apiGet,
  type AnalyticsSummary,
  type ApplicationState,
  type OutcomeKind,
} from "@/lib/api";

/** Counts, never a bare percentage: at these sample sizes one application moves
 * a rate by tens of points, and a lone "33%" invites reading a trend into three
 * data points. The rate is shown as the fraction it came from. */
function share(part: number, whole: number): string {
  if (whole === 0) return "nothing submitted yet";
  return `${part} of ${whole} submitted · ${Math.round((part / whole) * 100)}%`;
}

export default async function AnalyticsPage() {
  const summary = await apiGet<AnalyticsSummary>("/api/v1/analytics/");

  // One measure surviving each step, so the widths share a scale anchored to
  // the first stage rather than each bar being scaled to itself.
  const stages = [
    { label: "Started", count: summary.started },
    { label: "Submitted", count: summary.submitted },
    { label: "Responded", count: summary.responded },
    { label: "Interviewed", count: summary.interviewed },
    { label: "Offers", count: summary.offers },
  ];
  const scale = Math.max(summary.started, 1);

  const tiles = [
    { icon: BriefcaseIcon, label: "Submitted", value: summary.submitted, hint: "Sent to a company" },
    {
      icon: InboxIcon,
      label: "Responses",
      value: summary.responded,
      hint: share(summary.responded, summary.submitted),
    },
    {
      icon: ClipboardCheckIcon,
      label: "Interviews",
      value: summary.interviewed,
      hint: share(summary.interviewed, summary.submitted),
    },
    { icon: BarChartIcon, label: "Offers", value: summary.offers, hint: "Recorded offers" },
  ];

  const outcomes = Object.entries(summary.by_outcome) as [OutcomeKind, number][];
  const states = Object.entries(summary.by_state) as [ApplicationState, number][];

  return (
    <main>
      <div className="page-header-text">
        <h1>Analytics</h1>
        <p>
          Counted from what actually happened — an application only reaches a stage here once
          that stage was recorded, never inferred from a later one.
        </p>
      </div>

      {summary.started === 0 ? (
        <div className="empty-panel">
          <span className="empty-panel-icon">
            <BarChartIcon width={22} height={22} />
          </span>
          <h2>Nothing to measure yet</h2>
          <p>
            Start an application from a matched job and these fill in as it moves through the
            pipeline.
          </p>
        </div>
      ) : (
        <>
          <div className="stat-grid">
            {tiles.map(({ icon: Icon, label, value, hint }) => (
              <div key={label} className="stat-card">
                <span className="stat-card-icon">
                  <Icon width={18} height={18} />
                </span>
                <span className="stat-card-value">{value}</span>
                <span className="stat-card-label">{label}</span>
                <span className="stat-card-hint">{hint}</span>
              </div>
            ))}
          </div>

          <section className="card">
            <div className="card-head">
              <div className="card-head-text">
                <h2>Funnel</h2>
                <p className="text-muted text-small">
                  Applied → response → interview, the shape MVP.md asks for. An application that
                  interviewed and was later rejected still counts at the interview stage.
                </p>
              </div>
            </div>
            <div className="funnel">
              {stages.map(({ label, count }) => (
                <div key={label} className="funnel-row">
                  <span className="funnel-label">{label}</span>
                  <div className="funnel-track">
                    <div
                      className="funnel-bar"
                      style={{ width: `${(count / scale) * 100}%` }}
                      role="img"
                      aria-label={`${label}: ${count}`}
                    />
                  </div>
                  <span className="funnel-count">{count}</span>
                </div>
              ))}
            </div>
          </section>

          {outcomes.length > 0 && (
            <section className="card">
              <div className="card-head">
                <div className="card-head-text">
                  <h2>What came back</h2>
                  <p className="text-muted text-small">
                    Every recorded response, not one per application — the same application can
                    appear in two rows.
                  </p>
                </div>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Outcome</th>
                      <th>Recorded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outcomes.map(([kind, count]) => (
                      <tr key={kind}>
                        <td>{OUTCOME_KIND_LABELS[kind] ?? kind}</td>
                        <td>{count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="card">
            <div className="card-head">
              <div className="card-head-text">
                <h2>Resume variants</h2>
                <p className="text-muted text-small">
                  Counted over submitted applications only — one that was never sent could not
                  have drawn a reply, and would just dilute the rate.
                </p>
              </div>
            </div>
            {summary.variants.length === 0 ? (
              <p className="text-muted text-small">
                No submitted application has a tailored resume attached yet.
              </p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Variant</th>
                      <th>Submitted</th>
                      <th>Responded</th>
                      <th>Interviews</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.variants.map((variant) => (
                      <tr key={variant.variant_id}>
                        <td>{variant.role_label}</td>
                        <td>{variant.submitted}</td>
                        <td>{variant.responded}</td>
                        <td>{variant.interviews}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {summary.fill_runs > 0 && (
            <section className="card">
              <div className="card-head">
                <div className="card-head-text">
                  <h2>What the filler keeps leaving for you</h2>
                  <p className="text-muted text-small">
                    Across {summary.fill_runs} {summary.fill_runs === 1 ? "run" : "runs"} of the
                    form-filler. Ranked by applications affected rather than by raw count, since
                    one form filled three times over is one problem, not three. Two different
                    things land here: a control no adapter handles yet, and a question that was
                    refused on purpose — a sponsorship answer or a consent box is a skip working
                    correctly.
                  </p>
                </div>
              </div>
              {summary.skipped_fields.length === 0 ? (
                <p className="text-muted text-small">
                  Nothing was skipped in any recorded run.
                </p>
              ) : (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Field or question</th>
                        <th>Applications</th>
                        <th>Runs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.skipped_fields.map((skipped) => (
                        <tr key={skipped.field}>
                          <td>{skipped.field}</td>
                          <td>{skipped.applications}</td>
                          <td>{skipped.runs}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          <section className="card">
            <div className="card-head">
              <div className="card-head-text">
                <h2>Where everything sits</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>State</th>
                    <th>Applications</th>
                  </tr>
                </thead>
                <tbody>
                  {states.map(([state, count]) => (
                    <tr key={state}>
                      <td>{APPLICATION_STATE_LABELS[state] ?? state}</td>
                      <td>{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className="text-muted text-small">
            Not shown: time saved and LLM cost, both of which MVP.md lists. How long each fill
            takes is now measured and kept, but the manual baseline it would be subtracted from
            is not — nobody has timed filling these forms by hand — and no token spend is
            tracked either. Either figure would be an invented constant dressed up as a
            measurement.
          </p>
        </>
      )}
    </main>
  );
}
