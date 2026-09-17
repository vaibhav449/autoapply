import Link from "next/link";
import { ChevronRightIcon, PlusIcon, UsersIcon } from "@/components/icons";
import { apiGet, type ProfileOut } from "@/lib/api";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default async function ProfilesPage() {
  const profiles = await apiGet<ProfileOut[]>("/api/v1/profiles/");

  return (
    <main>
      <div className="page-header">
        <div className="page-header-text">
          <h1>Profiles</h1>
          <p>Each profile is a master resume plus preferences — the pipeline matches and tailors against it.</p>
        </div>
        <div className="page-header-actions">
          <Link href="/profiles/new" className="btn btn-primary">
            <PlusIcon width={16} height={16} />
            New profile
          </Link>
        </div>
      </div>

      {profiles.length === 0 ? (
        <div className="empty-panel">
          <span className="empty-panel-icon">
            <UsersIcon width={24} height={24} />
          </span>
          <h2>No profiles yet</h2>
          <p>Create your first profile to start discovering and ranking jobs against it.</p>
          <Link href="/profiles/new" className="btn btn-primary">
            <PlusIcon width={16} height={16} />
            Create your profile
          </Link>
        </div>
      ) : (
        <ul className="card-list">
          {profiles.map((profile) => (
            <li key={profile.id}>
              <Link href={`/profiles/${profile.id}`} className="list-row">
                <div className="list-row-main">
                  <span className="avatar" aria-hidden="true">
                    {initials(profile.name)}
                  </span>
                  <div className="list-row-body">
                    <span className="list-row-title">{profile.name}</span>
                    <span className="list-row-meta">
                      {profile.years_experience} yrs experience · {profile.projects.length} project
                      {profile.projects.length === 1 ? "" : "s"}
                    </span>
                  </div>
                </div>
                <ChevronRightIcon className="list-row-chevron" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
