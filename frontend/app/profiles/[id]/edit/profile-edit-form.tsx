"use client";

import { SubmitButton } from "@/components/submit-button";
import { ProfileFormFields } from "@/components/profile-form-fields";
import type { ProfileOut } from "@/lib/api";

export function ProfileEditForm({
  profile,
  action,
}: {
  profile: ProfileOut;
  action: (formData: FormData) => Promise<void>;
}) {
  return (
    <form action={action}>
      <ProfileFormFields
        defaults={{
          name: profile.name,
          email: profile.email,
          phone: profile.phone ?? undefined,
          location: profile.location ?? undefined,
          resumeText: profile.resume_text,
          targetLevel: profile.target_level,
          yearsExperience: profile.years_experience,
          remoteOnly: Boolean(profile.preferences?.remote_only),
          noticePeriod: profile.notice_period ?? undefined,
          currentCtc: profile.current_ctc ?? undefined,
          expectedCtc: profile.expected_ctc ?? undefined,
          preferredLocations: profile.preferred_locations ?? undefined,
          workAuthorization: profile.work_authorization ?? undefined,
          linkedinUrl: profile.linkedin_url ?? undefined,
          portfolioUrl: profile.portfolio_url ?? undefined,
          hasOfferInHand: profile.has_offer_in_hand,
        }}
        resumeHint="Changing this re-embeds your profile — it's what your matches are ranked against."
      />

      <div className="form-footer">
        <SubmitButton pendingLabel="Saving…">Save changes</SubmitButton>
      </div>
    </form>
  );
}
