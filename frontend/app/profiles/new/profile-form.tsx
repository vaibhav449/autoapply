"use client";

import { useState } from "react";
import { SubmitButton } from "@/components/submit-button";
import { PlusIcon, TrashIcon } from "@/components/icons";
import { TARGET_LEVEL_LABELS } from "@/lib/api";

type ProjectRow = { key: number; title: string; content: string };

export function ProfileForm({ action }: { action: (formData: FormData) => Promise<void> }) {
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [nextKey, setNextKey] = useState(0);

  function addProject() {
    setProjects((rows) => [...rows, { key: nextKey, title: "", content: "" }]);
    setNextKey((k) => k + 1);
  }

  function removeProject(key: number) {
    setProjects((rows) => rows.filter((r) => r.key !== key));
  }

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
            <input id="name" name="name" type="text" required />
          </div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" required />
          </div>

          <div className="field">
            <label htmlFor="phone">Phone (optional)</label>
            <input id="phone" name="phone" type="tel" />
          </div>

          <div className="field">
            <label htmlFor="location">Location (optional)</label>
            <input id="location" name="location" type="text" placeholder="e.g. Bengaluru, India" />
          </div>
        </div>
        <span className="field-hint">Email and phone go on your generated resume PDF and into application forms.</span>
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
          <span className="field-hint">Paste your resume text — this is what gets matched against job descriptions.</span>
          <textarea id="resume_text" name="resume_text" rows={10} required />
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
            <select id="target_level" name="target_level" defaultValue="junior" required>
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
              defaultValue={0}
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
            <input name="remote_only" type="checkbox" /> Remote only
          </label>
        </div>
      </section>

      <fieldset>
        <legend>Projects (in-depth write-ups)</legend>
        {projects.length === 0 && (
          <p className="field-hint">No projects added yet — optional, but improves match quality.</p>
        )}
        {projects.map((row) => (
          <div key={row.key} className="project-row">
            <div className="project-row-head">
              <input
                name="project_title"
                type="text"
                placeholder="Project title"
                defaultValue={row.title}
              />
              <button
                type="button"
                className="icon-button"
                onClick={() => removeProject(row.key)}
                aria-label="Remove project"
              >
                <TrashIcon width={15} height={15} />
              </button>
            </div>
            <textarea
              name="project_content"
              rows={4}
              placeholder="Project write-up (markdown)"
              defaultValue={row.content}
            />
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={addProject}>
          <PlusIcon width={15} height={15} />
          Add project
        </button>
      </fieldset>

      <div className="form-footer">
        <SubmitButton pendingLabel="Creating…">Create profile</SubmitButton>
      </div>
    </form>
  );
}
