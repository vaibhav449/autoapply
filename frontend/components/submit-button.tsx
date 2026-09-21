"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

export function SubmitButton({
  pendingLabel,
  children,
  variant = "primary",
}: {
  pendingLabel: string;
  children: ReactNode;
  /** Secondary for the alternatives sitting beside a screen's main action —
   * a review gate shouldn't give Approve and Reject the same weight. */
  variant?: "primary" | "secondary";
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={`btn btn-${variant}`} disabled={pending}>
      {pending ? pendingLabel : children}
    </button>
  );
}
