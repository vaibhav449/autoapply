import Link from "next/link";
import { apiGet, type ProfileOut } from "@/lib/api";

export default async function ProfilesPage() {
  const profiles = await apiGet<ProfileOut[]>("/api/v1/profiles/");

  return (
    <main>
      <h1>Profiles</h1>
      <div>
        <Link href="/profiles/new" className="btn">
          Create a new profile
        </Link>
      </div>
      {profiles.length === 0 ? (
        <p className="empty-state">No profiles yet.</p>
      ) : (
        <ul className="card-list">
          {profiles.map((profile) => (
            <li key={profile.id} className="card-list-item">
              <div>
                <div className="card-list-item-title">
                  <Link href={`/profiles/${profile.id}`}>{profile.name}</Link>
                </div>
                <div className="card-list-item-meta">
                  {profile.years_experience} yrs experience · {profile.projects.length} project
                  {profile.projects.length === 1 ? "" : "s"}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
