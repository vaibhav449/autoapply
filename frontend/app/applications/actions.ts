"use server";

import { redirect } from "next/navigation";
import {
  apiPatch,
  apiPost,
  type ApplicationCreateInput,
  type ApplicationOut,
  type ApplicationState,
  type DraftAnswerCreateInput,
  type DraftAnswerOut,
  type FillAttemptOut,
  type OutcomeKind,
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

  // null: the question asks for something only the candidate can supply (an
  // expected CTC, say) and their profile leaves it blank. The page explains
  // that and points at the profile instead of showing a made-up placeholder.
  const answer = await apiPost<DraftAnswerOut | null>(
    `/api/v1/applications/${applicationId}/draft-answers`,
    payload,
  );
  if (answer === null) {
    redirect(`/applications/${applicationId}?yours=${encodeURIComponent(questionText)}`);
  }

  // Redirect to the same page rather than revalidatePath: forces the same fresh
  // server-side fetch every other mutation in this app relies on, no new pattern.
  redirect(`/applications/${applicationId}`);
}

export async function recordOutcome(
  applicationId: number,
  formData: FormData,
): Promise<void> {
  const kind = String(formData.get("kind") ?? "") as OutcomeKind;

  if (!kind) {
    throw new Error("An outcome is required.");
  }

  const note = String(formData.get("note") ?? "").trim();

  await apiPost(`/api/v1/applications/${applicationId}/outcomes`, {
    kind,
    ...(note ? { note } : {}),
  });

  redirect(`/applications/${applicationId}`);
}

export async function updateDraftAnswer(
  applicationId: number,
  answerId: number,
  formData: FormData,
): Promise<void> {
  const answerText = String(formData.get("answer_text") ?? "").trim();

  if (!answerText) {
    throw new Error("An answer cannot be empty.");
  }

  await apiPatch(`/api/v1/applications/${applicationId}/draft-answers/${answerId}`, {
    answer_text: answerText,
  });

  // Back to the queue the edit came from, so a reviewer working through
  // answers stays where they are and sees the re-checked flags.
  const returnTo = String(formData.get("redirect_to") ?? "").trim();
  redirect(returnTo || `/applications/${applicationId}`);
}

// Called directly from a client component, not through a <form action> — the
// panel swaps in the new attempt the moment it lands, and a redirect back to
// this same page would make a long-running fill look like a page flash.
export async function fillApplicationForm(applicationId: number): Promise<FillAttemptOut> {
  return apiPost<FillAttemptOut>(`/api/v1/applications/${applicationId}/fill-form`, {});
}
