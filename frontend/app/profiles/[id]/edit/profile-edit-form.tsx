"use client";

import { SubmitButton } from "@/components/submit-button";
import { TARGET_LEVEL_LABELS, type ProfileOut } from "@/lib/api";

export function ProfileEditForm({
  profile,
  action,
}: {
  profile: ProfileOut;
  action: (formData: FormData) => Promise<void>;
}) {
  return (
    <form action={action}>
      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Basic info</h2>
          </div>
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" name="name" type="text" defaultValue={profile.name} required />
          </div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" defaultValue={profile.email} required />
          </div>

          <div className="field">
            <label htmlFor="phone">Phone (optional)</label>
            <input id="phone" name="phone" type="tel" defaultValue={profile.phone ?? ""} />
          </div>

          <div className="field">
            <label htmlFor="location">Location (optional)</label>
            <input
              id="location"
              name="location"
              type="text"
              placeholder="e.g. Bengaluru, India"
              defaultValue={profile.location ?? ""}
            />
          </div>
        </div>
        <span className="field-hint">
          Email and phone go on your generated resume PDF and into application forms.
        </span>
      </section>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Master resume</h2>
          </div>
        </div>
        <div className="field">
          <label htmlFor="resume_text" className="sr-only">
            Master resume
          </label>
          <span className="field-hint">
            Changing this re-embeds your profile — it&apos;s what your matches are ranked
            against.
          </span>
          <textarea
            id="resume_text"
            name="resume_text"
            rows={10}
            defaultValue={profile.resume_text}
            required
          />
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>What are you looking for?</h2>
          </div>
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="target_level">Target level</label>
            <select
              id="target_level"
              name="target_level"
              defaultValue={profile.target_level}
              required
            >
              {Object.entries(TARGET_LEVEL_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="years_experience">Years of experience</label>
            <input
              id="years_experience"
              name="years_experience"
              type="number"
              step="0.5"
              min="0"
              defaultValue={profile.years_experience}
              required
            />
          </div>
        </div>
        <span className="field-hint">
          Target level decides which jobs get collected in the first place — not just how
          they&apos;re ranked. Set it to what you want next, not what you already have.
        </span>

        <div className="field checkbox-field">
          <label>
            <input
              name="remote_only"
              type="checkbox"
              defaultChecked={Boolean(profile.preferences?.remote_only)}
            />{" "}
            Remote only
          </label>
        </div>
      </section>

      <div className="form-footer">
        <SubmitButton pendingLabel="Saving…">Save changes</SubmitButton>
      </div>
    </form>
  );
}
