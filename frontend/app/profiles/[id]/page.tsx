import Link from "next/link";
import { apiGet, type JobMatch, type ProfileOut } from "@/lib/api";

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

  return (
    <main>
      <div>
        <Link href="/profiles">← All profiles</Link>
      </div>

      <div>
        <h1>{profile.name}</h1>
        <p>
          {profile.years_experience} years of experience
          {Boolean(profile.preferences?.remote_only) && " · Prefers remote only"}
        </p>
      </div>

      <div>
        <Link href={`/profiles/${id}/resumes`} className="btn">
          Resume variants
        </Link>
      </div>

      <section className="card">
        <h2>Master resume</h2>
        <pre>{profile.resume_text}</pre>
      </section>

      {profile.projects.length > 0 && (
        <section className="card">
          <h2>Projects</h2>
          {profile.projects.map((project) => (
            <div key={project.id}>
              <h3>{project.title}</h3>
              <pre>{project.content_md}</pre>
            </div>
          ))}
        </section>
      )}

      <section>
        <h2>Matching jobs</h2>
        {matchesError && <p className="empty-state">{matchesError}</p>}
        {!matchesError && matches.length === 0 && (
          <p className="empty-state">No matches yet — check back after the next discovery run.</p>
        )}
        {!matchesError && matches.length > 0 && (
          <ul className="match-list">
            {matches.map(({ job, score }) => (
              <li key={job.id} className="match-item">
                <div className="match-item-body">
                  <a href={job.url} target="_blank" rel="noreferrer">
                    {job.title}
                  </a>
                  <span className="match-item-company">
                    {job.company}
                    {job.location ? ` · ${job.location}` : ""}
                  </span>
                  <Link href={`/profiles/${id}/jobs/${job.id}/cover-letter`}>
                    Generate cover letter →
                  </Link>
                </div>
                <span className="score-badge">{score.toFixed(3)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
