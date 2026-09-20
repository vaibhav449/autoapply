"use server";

import { redirect } from "next/navigation";
import {
  apiPatch,
  apiPost,
  type ApplicationAnswers,
  type ProfileCreateInput,
  type ProfileOut,
  type ProfileUpdateInput,
  type ResumeVariantCreateInput,
  type TargetLevel,
} from "@/lib/api";

type ParsedProfileFields = {
  name: string;
  email: string;
  phone: string;
  location: string;
  resumeText: string;
  yearsExperience: number;
  targetLevel: TargetLevel;
  remoteOnly: boolean;
  applicationAnswers: ApplicationAnswers;
};

/** Blank means "not provided", which has to reach the backend as null rather
 * than "" — the prompt builder only lists fields the candidate actually
 * answered, and a stored "" would be an answer that renders as nothing. Same
 * mapping serves create and update: null is "unanswered" on one and "cleared"
 * on the other. */
function parseApplicationAnswers(formData: FormData): ApplicationAnswers {
  const text = (field: string) => String(formData.get(field) ?? "").trim() || null;
  const offer = String(formData.get("has_offer_in_hand") ?? "");

  return {
    notice_period: text("notice_period"),
    current_ctc: text("current_ctc"),
    expected_ctc: text("expected_ctc"),
    preferred_locations: text("preferred_locations"),
    work_authorization: text("work_authorization"),
    linkedin_url: text("linkedin_url"),
    portfolio_url: text("portfolio_url"),
    // "" is the deliberate "prefer not to say" option, and must stay distinct
    // from a definite No — the form is left for the human either way, but only
    // one of them is an answer.
    has_offer_in_hand: offer === "" ? null : offer === "true",
  };
}

/** Shared by createProfile and updateProfile: same fields, same shape, same
 * required-field rule. They differ only in what they do with the result —
 * create omits empty phone/location, update sends them (see below) — so that
 * divergence stays in each action, not duplicated here too. */
function parseProfileFormFields(
  formData: FormData,
  defaultTargetLevel: TargetLevel | "" = "",
): ParsedProfileFields {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const location = String(formData.get("location") ?? "").trim();
  const resumeText = String(formData.get("resume_text") ?? "").trim();
  const yearsExperience = Number(formData.get("years_experience") ?? 0);
  const targetLevel = String(formData.get("target_level") ?? defaultTargetLevel) as TargetLevel;
  const remoteOnly = formData.get("remote_only") === "on";

  if (!name || !email || !resumeText) {
    throw new Error("Name, email, and resume text are required.");
  }

  return {
    name,
    email,
    phone,
    location,
    resumeText,
    yearsExperience,
    targetLevel,
    remoteOnly,
    applicationAnswers: parseApplicationAnswers(formData),
  };
}

export async function createProfile(formData: FormData): Promise<void> {
  const fields = parseProfileFormFields(formData, "mid");

  const projectTitles = formData.getAll("project_title") as string[];
  const projectContents = formData.getAll("project_content") as string[];
  const projects = projectTitles
    .map((title, i) => ({ title: title.trim(), content_md: (projectContents[i] ?? "").trim() }))
    .filter((p) => p.title && p.content_md);

  const payload: ProfileCreateInput = {
    name: fields.name,
    email: fields.email,
    ...(fields.phone ? { phone: fields.phone } : {}),
    ...(fields.location ? { location: fields.location } : {}),
    resume_text: fields.resumeText,
    years_experience: fields.yearsExperience,
    target_level: fields.targetLevel,
    preferences: { remote_only: fields.remoteOnly },
    projects,
    ...fields.applicationAnswers,
  };

  const profile = await apiPost<ProfileOut>("/api/v1/profiles/", payload);

  redirect(`/profiles/${profile.id}`);
}

export async function updateProfile(profileId: number, formData: FormData): Promise<void> {
  const fields = parseProfileFormFields(formData);

  const payload: ProfileUpdateInput = {
    name: fields.name,
    email: fields.email,
    // phone/location CAN be intentionally cleared here (unlike create, there's
    // an existing value to remove), so an empty field sends "" rather than being
    // omitted — omitting would leave the old value in place instead.
    phone: fields.phone,
    location: fields.location,
    resume_text: fields.resumeText,
    years_experience: fields.yearsExperience,
    target_level: fields.targetLevel,
    preferences: { remote_only: fields.remoteOnly },
    ...fields.applicationAnswers,
  };

  await apiPatch<ProfileOut>(`/api/v1/profiles/${profileId}`, payload);

  redirect(`/profiles/${profileId}`);
}

export async function createResumeVariant(profileId: number, formData: FormData): Promise<void> {
  const roleLabel = String(formData.get("role_label") ?? "").trim();
  const emphasisNote = String(formData.get("emphasis_note") ?? "").trim();

  if (!roleLabel) {
    throw new Error("Role label is required.");
  }

  const payload: ResumeVariantCreateInput = {
    role_label: roleLabel,
    ...(emphasisNote ? { emphasis_note: emphasisNote } : {}),
  };

  await apiPost(`/api/v1/profiles/${profileId}/resume-variants`, payload);

  redirect(`/profiles/${profileId}/resumes`);
}
