import Link from "next/link";
import { ChevronRightIcon, ExternalLinkIcon } from "@/components/icons";
import type { JobMatch, MatchTier } from "@/lib/api";

const TIER_COPY: Record<MatchTier, { label: string; hint: string }> = {
  qualified: {
    label: "Qualified",
    hint: "You meet the experience requirement the posting states.",
  },
  stretch: {
    label: "Stretch",
    hint: "Reachable, but the posting asks for more experience than you listed.",
  },
  unverified: {
    label: "Unverified",
    hint: "The posting never stated its requirements, so nothing could be checked.",
  },
  excluded: {
    label: "Excluded",
    hint: "You match none of the technologies this posting requires.",
  },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function MatchList({
  matches,
  profileId,
}: {
  matches: JobMatch[];
  profileId: string;
}) {
  return (
    <ul className="match-list">
      {matches.map(({ job, score, tier, note, stale }) => {
        // Falls back rather than crashing: tier arrives from the API, and a new
        // tier added server-side shouldn't blank the page.
        const copy = TIER_COPY[tier] ?? { label: tier, hint: "" };
        const percent = Math.max(0, Math.min(100, Math.round(score * 100)));

        return (
          <li key={job.id} className="match-item">
            <div className="match-item-main">
              <span className="avatar" aria-hidden="true">
                {initials(job.company)}
              </span>

              <div className="match-item-body">
                <div className="match-item-head">
                  <span className={`tier-badge tier-${tier}`} title={copy.hint}>
                    {copy.label}
                  </span>
                  {stale && (
                    <span
                      className="tier-badge tier-stale"
                      title="This posting hasn't appeared in a recent poll. It may already be closed — open it to check."
                    >
                      Stale
                    </span>
                  )}
                  <a href={job.url} target="_blank" rel="noreferrer">
                    {job.title}
                    <ExternalLinkIcon width={14} height={14} />
                  </a>
                </div>

                <span className="match-item-company">
                  {job.company}
                  {job.location ? ` · ${job.location}` : ""}
                </span>

                {note && (
                  <ul className="match-note">
                    {note.split(" · ").map((part) => (
                      <li key={part}>{part}</li>
                    ))}
                  </ul>
                )}

                <Link
                  href={`/profiles/${profileId}/jobs/${job.id}/cover-letter`}
                  className="match-item-footer"
                >
                  Generate cover letter
                  <ChevronRightIcon width={14} height={14} />
                </Link>
              </div>
            </div>

            <div className="match-item-aside">
              <div className="score-meter">
                <span className="score-meter-value">{score.toFixed(3)}</span>
                <span className="score-meter-track">
                  <span className="score-meter-fill" style={{ width: `${percent}%` }} />
                </span>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
