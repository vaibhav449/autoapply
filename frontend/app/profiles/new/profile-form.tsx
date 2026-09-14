"use client";

import { useState } from "react";
import { SubmitButton } from "@/components/submit-button";

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
      <div className="field">
        <label htmlFor="name">Name</label>
        <input id="name" name="name" type="text" required />
      </div>

      <div className="field">
        <label htmlFor="resume_text">Master resume</label>
        <span className="field-hint">Paste your resume text — this is what gets matched against job descriptions.</span>
        <textarea id="resume_text" name="resume_text" rows={10} required />
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

      <div className="field checkbox-field">
        <label>
          <input name="remote_only" type="checkbox" /> Remote only
        </label>
      </div>

      <fieldset>
        <legend>Projects (in-depth write-ups)</legend>
        {projects.length === 0 && <p className="field-hint">No projects added yet — optional, but improves match quality.</p>}
        {projects.map((row) => (
          <div key={row.key} className="project-row">
            <input
              name="project_title"
              type="text"
              placeholder="Project title"
              defaultValue={row.title}
            />
            <textarea
              name="project_content"
              rows={4}
              placeholder="Project write-up (markdown)"
              defaultValue={row.content}
            />
            <button type="button" onClick={() => removeProject(row.key)}>
              Remove project
            </button>
          </div>
        ))}
        <button type="button" onClick={addProject}>
          + Add project
        </button>
      </fieldset>

      <SubmitButton pendingLabel="Creating…">Create profile</SubmitButton>
    </form>
  );
}
