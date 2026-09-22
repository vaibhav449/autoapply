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

/** The answers a resume can't supply, which real application forms ask on
 * nearly every posting. null means the candidate hasn't answered — which is
 * left blank on the form rather than guessed. */
export type ApplicationAnswers = {
  notice_period: string | null;
  current_ctc: string | null;
  expected_ctc: string | null;
  preferred_locations: string | null;
  work_authorization: string | null;
  linkedin_url: string | null;
  portfolio_url: string | null;
  has_offer_in_hand: boolean | null;
};

export type ProfileCreateInput = Partial<ApplicationAnswers> & {
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
export type ProfileUpdateInput = Partial<
  ApplicationAnswers & {
    name: string;
    email: string;
    phone: string;
    location: string;
    resume_text: string;
    years_experience: number;
    target_level: TargetLevel;
    preferences: Record<string, unknown>;
  }
>;

export type ProfileProjectOut = {
  id: number;
  title: string;
  content_md: string;
};

export type ProfileOut = ApplicationAnswers & {
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

export type ApplicationState =
  | "interested"
  | "tailoring"
  | "ready_for_review"
  | "pending_captcha"
  | "approved"
  | "rejected_by_user"
  | "submitted"
  | "response_tracked";

export const APPLICATION_STATE_LABELS: Record<ApplicationState, string> = {
  interested: "Interested",
  tailoring: "Tailoring",
  ready_for_review: "Ready for review",
  pending_captcha: "Pending CAPTCHA",
  approved: "Approved",
  rejected_by_user: "Rejected",
  submitted: "Submitted",
  response_tracked: "Response tracked",
};

export type ApplicationOut = {
  id: number;
  profile_id: number;
  job_id: number;
  state: ApplicationState;
  cover_letter_id: number | null;
  resume_variant_id: number | null;
  created_at: string;
  submitted_at: string | null;
  // From Application.legal_next_states on the backend — the one real edge
  // list, so transition buttons never need a hand-copied state-machine map.
  legal_next_states: ApplicationState[];
};

export type ApplicationCreateInput = {
  profile_id: number;
  job_id: number;
};

export type DraftAnswerCreateInput = {
  question_text: string;
};

export type DraftAnswerOut = {
  id: number;
  application_id: number;
  question_text: string;
  answer_text: string;
  unverified_claims: string[];
  created_at: string;
};

export type VariantPerformance = {
  variant_id: number;
  role_label: string;
  submitted: number;
  responded: number;
  interviews: number;
};

export type AnalyticsSummary = {
  started: number;
  submitted: number;
  responded: number;
  interviewed: number;
  offers: number;
  by_state: Record<string, number>;
  by_outcome: Record<string, number>;
  variants: VariantPerformance[];
};

/** What came back after an application went out. Recorded as a log, not a
 * state: an application that interviewed and was then rejected has to count in
 * both for the funnel, which a single current-state value can't express. */
export type OutcomeKind = "no_response" | "rejected" | "interview" | "offer";

export const OUTCOME_KIND_LABELS: Record<OutcomeKind, string> = {
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  no_response: "No response",
};

export type ApplicationOutcomeOut = {
  id: number;
  application_id: number;
  kind: OutcomeKind;
  note: string | null;
  occurred_at: string;
  created_at: string;
};

export type FillFormStatus = "filled" | "captcha_required" | "form_not_found";

export type FillFormResultOut = {
  status: FillFormStatus;
  filled_fields: Record<string, string>;
  skipped_fields: string[];
  screenshot_base64: string | null;
};

export type ResumeVariantOut = {
  id: number;
  role_label: string;
  emphasis_note: string | null;
  generated_content: string;
  unverified_claims: string[];
  created_at: string;
};
