// Exported because some resources (the resume PDF) are linked to directly in the
// browser rather than fetched through apiGet.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`POST ${path} failed: ${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`PATCH ${path} failed: ${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export type ProfileProjectCreate = {
  title: string;
  content_md: string;
};

/** What the candidate wants next — drives which jobs discovery even collects. */
export type TargetLevel = "intern" | "new_grad" | "junior" | "mid" | "senior";

export const TARGET_LEVEL_LABELS: Record<TargetLevel, string> = {
  intern: "Internship",
  new_grad: "New graduate / fresher",
  junior: "Junior (0–2 years)",
  mid: "Mid-level (3–6 years)",
  senior: "Senior (7+ years)",
};

export type ProfileCreateInput = {
  name: string;
  email: string;
  phone?: string;
  location?: string;
  resume_text: string;
  years_experience: number;
  target_level: TargetLevel;
  preferences?: Record<string, unknown>;
  projects?: ProfileProjectCreate[];
};

/** Every field optional: only the ones present in the FormData get sent, so a
 * blank input never clobbers a value the user didn't mean to touch. */
export type ProfileUpdateInput = Partial<{
  name: string;
  email: string;
  phone: string;
  location: string;
  resume_text: string;
  years_experience: number;
  target_level: TargetLevel;
  preferences: Record<string, unknown>;
}>;

export type ProfileProjectOut = {
  id: number;
  title: string;
  content_md: string;
};

export type ProfileOut = {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  location: string | null;
  resume_text: string;
  years_experience: number;
  target_level: TargetLevel;
  preferences: Record<string, unknown>;
  created_at: string;
  projects: ProfileProjectOut[];
};

export type JobOut = {
  id: number;
  external_id: string;
  source: string;
  title: string;
  company: string;
  location: string | null;
  url: string;
  description: string | null;
  discovered_at: string;
};

export type MatchTier = "qualified" | "stretch" | "unverified" | "excluded";

export type JobMatch = {
  job: JobOut;
  score: number;
  tier: MatchTier;
  experience: "pass" | "fail" | "unknown";
  /** Human-readable gaps, " · "-separated, quoting the source sentence. */
  note: string | null;
  /** Not seen in a recent poll — a warning, never a claim that it closed. */
  stale: boolean;
};

export type CoverLetterOut = {
  id: number;
  job_id: number;
  content: string;
  created_at: string;
};

export type ResumeVariantCreateInput = {
  role_label: string;
  emphasis_note?: string;
};

export type ResumeVariantOut = {
  id: number;
  role_label: string;
  emphasis_note: string | null;
  generated_content: string;
  unverified_claims: string[];
  created_at: string;
};
