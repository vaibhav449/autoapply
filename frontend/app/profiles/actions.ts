"use server";

import { redirect } from "next/navigation";
import {
  apiPatch,
  apiPost,
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
};

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

  return { name, email, phone, location, resumeText, yearsExperience, targetLevel, remoteOnly };
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
