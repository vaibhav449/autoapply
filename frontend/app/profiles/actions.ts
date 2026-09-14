"use server";

import { redirect } from "next/navigation";
import {
  apiPost,
  type ProfileCreateInput,
  type ProfileOut,
  type ResumeVariantCreateInput,
} from "@/lib/api";

export async function createProfile(formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const resumeText = String(formData.get("resume_text") ?? "").trim();
  const yearsExperience = Number(formData.get("years_experience") ?? 0);
  const remoteOnly = formData.get("remote_only") === "on";

  if (!name || !resumeText) {
    throw new Error("Name and resume text are required.");
  }

  const projectTitles = formData.getAll("project_title") as string[];
  const projectContents = formData.getAll("project_content") as string[];
  const projects = projectTitles
    .map((title, i) => ({ title: title.trim(), content_md: (projectContents[i] ?? "").trim() }))
    .filter((p) => p.title && p.content_md);

  const payload: ProfileCreateInput = {
    name,
    resume_text: resumeText,
    years_experience: yearsExperience,
    preferences: { remote_only: remoteOnly },
    projects,
  };

  const profile = await apiPost<ProfileOut>("/api/v1/profiles/", payload);

  redirect(`/profiles/${profile.id}`);
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
