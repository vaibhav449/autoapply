const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export type ProfileProjectCreate = {
  title: string;
  content_md: string;
};

export type ProfileCreateInput = {
  name: string;
  resume_text: string;
  years_experience: number;
  preferences?: Record<string, unknown>;
  projects?: ProfileProjectCreate[];
};

export type ProfileProjectOut = {
  id: number;
  title: string;
  content_md: string;
};

export type ProfileOut = {
  id: number;
  name: string;
  resume_text: string;
  years_experience: number;
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

export type JobMatch = {
  job: JobOut;
  score: number;
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
