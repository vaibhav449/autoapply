"use client";

import { useState } from "react";
import { SubmitButton } from "@/components/submit-button";
import { ProfileFormFields } from "@/components/profile-form-fields";
import { PlusIcon, TrashIcon } from "@/components/icons";

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
      <ProfileFormFields resumeHint="Paste your resume text — this is what gets matched against job descriptions." />

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
