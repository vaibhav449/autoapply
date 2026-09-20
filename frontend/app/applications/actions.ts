"use server";

import { redirect } from "next/navigation";
import {
  apiPost,
  type ApplicationCreateInput,
  type ApplicationOut,
  type ApplicationState,
  type DraftAnswerCreateInput,
  type FillFormResultOut,
} from "@/lib/api";

export async function startApplication(profileId: number, jobId: number): Promise<void> {
  const payload: ApplicationCreateInput = { profile_id: profileId, job_id: jobId };

  // Idempotent on the backend (get_or_create_application), so clicking this
  // twice for the same job just lands back on the same application.
  const application = await apiPost<ApplicationOut>("/api/v1/applications/", payload);

  redirect(`/applications/${application.id}`);
}

export async function transitionApplication(
  applicationId: number,
  formData: FormData,
): Promise<void> {
  const targetState = String(formData.get("target_state") ?? "") as ApplicationState;

  if (!targetState) {
    throw new Error("A target state is required.");
  }

  await apiPost(`/api/v1/applications/${applicationId}/transition`, {
    target_state: targetState,
  });

  // A queue screen passes its own path so working through a list leaves you on
  // the list, with the row you just handled gone from it.
  const returnTo = String(formData.get("redirect_to") ?? "").trim();
  const destination = returnTo || `/applications/${applicationId}`;

  redirect(destination);
}

export async function createDraftAnswer(
  applicationId: number,
  formData: FormData,
): Promise<void> {
  const questionText = String(formData.get("question_text") ?? "").trim();

  if (!questionText) {
    throw new Error("A question is required.");
  }

  const payload: DraftAnswerCreateInput = { question_text: questionText };

  await apiPost(`/api/v1/applications/${applicationId}/draft-answers`, payload);

  // Redirect to the same page rather than revalidatePath: forces the same fresh
  // server-side fetch every other mutation in this app relies on, no new pattern.
  redirect(`/applications/${applicationId}`);
}

// Called directly from a client component, not through a <form action> — the
// real, per-run result (filled fields, a fresh screenshot) only makes sense
// rendered inline, and a redirect back to this same page would throw it away
// rather than display it.
export async function fillApplicationForm(applicationId: number): Promise<FillFormResultOut> {
  return apiPost<FillFormResultOut>(`/api/v1/applications/${applicationId}/fill-form`, {});
}
