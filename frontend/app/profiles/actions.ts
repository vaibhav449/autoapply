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

export async function createProfile(formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const location = String(formData.get("location") ?? "").trim();
  const resumeText = String(formData.get("resume_text") ?? "").trim();
  const yearsExperience = Number(formData.get("years_experience") ?? 0);
  const targetLevel = String(formData.get("target_level") ?? "mid") as TargetLevel;
  const remoteOnly = formData.get("remote_only") === "on";

  if (!name || !email || !resumeText) {
    throw new Error("Name, email, and resume text are required.");
  }

  const projectTitles = formData.getAll("project_title") as string[];
  const projectContents = formData.getAll("project_content") as string[];
  const projects = projectTitles
    .map((title, i) => ({ title: title.trim(), content_md: (projectContents[i] ?? "").trim() }))
    .filter((p) => p.title && p.content_md);

  const payload: ProfileCreateInput = {
    name,
    email,
    ...(phone ? { phone } : {}),
    ...(location ? { location } : {}),
    resume_text: resumeText,
    years_experience: yearsExperience,
    target_level: targetLevel,
    preferences: { remote_only: remoteOnly },
    projects,
  };

  const profile = await apiPost<ProfileOut>("/api/v1/profiles/", payload);

  redirect(`/profiles/${profile.id}`);
}

export async function updateProfile(profileId: number, formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const location = String(formData.get("location") ?? "").trim();
  const resumeText = String(formData.get("resume_text") ?? "").trim();
  const yearsExperience = Number(formData.get("years_experience") ?? 0);
  const targetLevel = String(formData.get("target_level") ?? "") as TargetLevel;
  const remoteOnly = formData.get("remote_only") === "on";

  if (!name || !email || !resumeText) {
    throw new Error("Name, email, and resume text are required.");
  }

  const payload: ProfileUpdateInput = {
    name,
    email,
    // phone/location CAN be intentionally cleared here (unlike create, there's
    // an existing value to remove), so an empty field sends "" rather than being
    // omitted — omitting would leave the old value in place instead.
    phone,
    location,
    resume_text: resumeText,
    years_experience: yearsExperience,
    target_level: targetLevel,
    preferences: { remote_only: remoteOnly },
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
