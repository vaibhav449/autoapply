import Link from "next/link";
import { MatchList } from "@/components/match-list";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  FileTextIcon,
  MailIcon,
  MapPinIcon,
  PencilIcon,
  PhoneIcon,
} from "@/components/icons";
import {
  apiGet,
  TARGET_LEVEL_LABELS,
  type JobMatch,
  type ProfileOut,
} from "@/lib/api";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default async function ProfileDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const profile = await apiGet<ProfileOut>(`/api/v1/profiles/${id}`);

  let matches: JobMatch[] = [];
  let matchesError: string | null = null;
  try {
    matches = await apiGet<JobMatch[]>(`/api/v1/profiles/${id}/matches`);
  } catch {
    matchesError = "Matches aren't ready yet — try refreshing in a moment.";
  }

  const qualifiedCount = matches.filter((m) => m.tier === "qualified").length;

  return (
    <main>
      <Link href="/profiles" className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        All profiles
      </Link>

      <div className="page-header">
        <div className="page-header-text page-header-identity">
          <span className="avatar avatar-lg" aria-hidden="true">
            {initials(profile.name)}
          </span>
          <div className="page-header-identity-text">
            <h1>{profile.name}</h1>
            <p>
              Looking for {TARGET_LEVEL_LABELS[profile.target_level] ?? profile.target_level}
              {" · "}
              {profile.years_experience} years of experience
              {Boolean(profile.preferences?.remote_only) && " · Prefers remote only"}
            </p>
            <div className="contact-row">
              {profile.email && (
                <span className="contact-chip">
                  <MailIcon width={14} height={14} />
                  {profile.email}
                </span>
              )}
              {profile.phone && (
                <span className="contact-chip">
                  <PhoneIcon width={14} height={14} />
                  {profile.phone}
                </span>
              )}
              {profile.location && (
                <span className="contact-chip">
                  <MapPinIcon width={14} height={14} />
                  {profile.location}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="page-header-actions">
          <Link href={`/profiles/${id}/edit`} className="btn btn-secondary">
            <PencilIcon width={16} height={16} />
            Edit profile
          </Link>
          <Link href={`/profiles/${id}/resumes`} className="btn btn-secondary">
            <FileTextIcon width={16} height={16} />
            Resume variants
          </Link>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Master resume</h2>
          </div>
        </div>
        <div className="document">{profile.resume_text}</div>
      </section>

      {profile.projects.length > 0 && (
        <section className="section">
          <h2>Projects</h2>
          {profile.projects.map((project) => (
            <div key={project.id} className="card">
              <div className="card-head">
                <div className="card-head-text">
                  <h3>{project.title}</h3>
                </div>
              </div>
              <div className="document">{project.content_md}</div>
            </div>
          ))}
        </section>
      )}

      <section className="section">
        <div className="section-head">
          <h2>Matching jobs</h2>
        </div>
        <p className="text-muted text-small">
          Ordered by how well the posting could be checked against you, then by similarity.
          Closed postings are excluded entirely.
        </p>
        {matchesError && (
          <div className="alert alert-info">
            <AlertTriangleIcon className="alert-icon" width={18} height={18} />
            <div className="alert-body">
              <p>{matchesError}</p>
            </div>
          </div>
        )}
        {!matchesError && matches.length === 0 && (
          <p className="empty-state">No matches yet — check back after the next discovery run.</p>
        )}
        {/* Ten unreachable jobs presented without comment reads as "your matches".
            Say plainly when nothing actually fits. */}
        {!matchesError && matches.length > 0 && qualifiedCount === 0 && (
          <div className="alert alert-warning">
            <AlertTriangleIcon className="alert-icon" width={18} height={18} />
            <div className="alert-body">
              <strong>Nothing here matches your experience level yet</strong>
              <p>
                Every job below asks for more experience than you listed, or couldn&apos;t be
                checked. That&apos;s a gap in what has been collected, not a ranking problem — the
                boards being polled are mostly hiring above your level.
              </p>
              <p>
                Searches are generated from the level on your profile, so the next discovery run
                will look specifically for{" "}
                {TARGET_LEVEL_LABELS[profile.target_level] ?? profile.target_level} roles.
              </p>
            </div>
          </div>
        )}
        {!matchesError && matches.length > 0 && <MatchList matches={matches} profileId={id} />}
      </section>
    </main>
  );
}
