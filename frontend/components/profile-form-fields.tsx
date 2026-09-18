import { TARGET_LEVEL_LABELS, type TargetLevel } from "@/lib/api";

type ProfileFormDefaults = {
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  resumeText?: string;
  targetLevel?: TargetLevel;
  yearsExperience?: number;
  remoteOnly?: boolean;
};

/**
 * The "Basic info" / "Master resume" / "What are you looking for?" card
 * sections shared by the create and edit profile forms. The only real
 * differences between those two flows are the default values pre-filled here
 * and the resume-text hint copy — both passed in as props — plus what each
 * form renders before/after this (create adds a Projects fieldset; both use a
 * different submit-button label).
 */
export function ProfileFormFields({
  defaults = {},
  resumeHint,
}: {
  defaults?: ProfileFormDefaults;
  resumeHint: string;
}) {
  return (
    <>
      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Basic info</h2>
          </div>
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" name="name" type="text" defaultValue={defaults.name} required />
          </div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" defaultValue={defaults.email} required />
          </div>

          <div className="field">
            <label htmlFor="phone">Phone (optional)</label>
            <input id="phone" name="phone" type="tel" defaultValue={defaults.phone} />
          </div>

          <div className="field">
            <label htmlFor="location">Location (optional)</label>
            <input
              id="location"
              name="location"
              type="text"
              placeholder="e.g. Bengaluru, India"
              defaultValue={defaults.location}
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
          <span className="field-hint">{resumeHint}</span>
          <textarea
            id="resume_text"
            name="resume_text"
            rows={10}
            defaultValue={defaults.resumeText}
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
              defaultValue={defaults.targetLevel ?? "junior"}
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
              defaultValue={defaults.yearsExperience ?? 0}
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
            <input name="remote_only" type="checkbox" defaultChecked={defaults.remoteOnly} />{" "}
            Remote only
          </label>
        </div>
      </section>
    </>
  );
}
