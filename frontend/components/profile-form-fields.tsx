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
  noticePeriod?: string;
  currentCtc?: string;
  expectedCtc?: string;
  preferredLocations?: string;
  workAuthorization?: string;
  linkedinUrl?: string;
  portfolioUrl?: string;
  hasOfferInHand?: boolean | null;
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

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Application answers</h2>
            <p className="text-muted text-small">
              Questions almost every application form asks that a resume can&apos;t answer.
              Fill them in once and form-filling uses them everywhere. Anything left blank
              is left blank on the form too — never guessed.
            </p>
          </div>
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="notice_period">Notice period / when you can start</label>
            <input
              id="notice_period"
              name="notice_period"
              type="text"
              placeholder="e.g. 30 days, negotiable"
              defaultValue={defaults.noticePeriod}
            />
          </div>

          <div className="field">
            <label htmlFor="preferred_locations">Preferred work locations</label>
            <input
              id="preferred_locations"
              name="preferred_locations"
              type="text"
              placeholder="e.g. Bengaluru, Pune, Remote"
              defaultValue={defaults.preferredLocations}
            />
          </div>

          <div className="field">
            <label htmlFor="current_ctc">Current CTC</label>
            <input
              id="current_ctc"
              name="current_ctc"
              type="text"
              placeholder="e.g. 6 LPA"
              defaultValue={defaults.currentCtc}
            />
          </div>

          <div className="field">
            <label htmlFor="expected_ctc">Expected CTC</label>
            <input
              id="expected_ctc"
              name="expected_ctc"
              type="text"
              placeholder="e.g. 12 LPA"
              defaultValue={defaults.expectedCtc}
            />
          </div>

          <div className="field">
            <label htmlFor="work_authorization">Work authorization</label>
            <input
              id="work_authorization"
              name="work_authorization"
              type="text"
              placeholder="e.g. Indian citizen, no sponsorship needed"
              defaultValue={defaults.workAuthorization}
            />
          </div>

          <div className="field">
            <label htmlFor="has_offer_in_hand">Another offer in hand?</label>
            <select
              id="has_offer_in_hand"
              name="has_offer_in_hand"
              defaultValue={
                defaults.hasOfferInHand === undefined || defaults.hasOfferInHand === null
                  ? ""
                  : String(defaults.hasOfferInHand)
              }
            >
              <option value="">Prefer not to say</option>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="linkedin_url">LinkedIn</label>
            <input
              id="linkedin_url"
              name="linkedin_url"
              type="url"
              placeholder="https://linkedin.com/in/…"
              defaultValue={defaults.linkedinUrl}
            />
          </div>

          <div className="field">
            <label htmlFor="portfolio_url">Portfolio / GitHub</label>
            <input
              id="portfolio_url"
              name="portfolio_url"
              type="url"
              placeholder="https://github.com/…"
              defaultValue={defaults.portfolioUrl}
            />
          </div>
        </div>
        <span className="field-hint">
          &quot;Prefer not to say&quot; on the offer question leaves it for you to answer
          during review, which is different from answering No.
        </span>
      </section>
    </>
  );
}
