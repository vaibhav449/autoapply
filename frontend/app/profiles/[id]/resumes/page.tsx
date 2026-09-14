import Link from "next/link";
import { apiGet, type ResumeVariantOut } from "@/lib/api";
import { createResumeVariant } from "@/app/profiles/actions";
import { SubmitButton } from "@/components/submit-button";

export default async function ResumeVariantsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const profileId = Number(id);
  const variants = await apiGet<ResumeVariantOut[]>(`/api/v1/profiles/${id}/resume-variants`);

  const createWithProfileId = createResumeVariant.bind(null, profileId);

  return (
    <main>
      <div>
        <Link href={`/profiles/${id}`}>← Back to profile</Link>
      </div>

      <div>
        <h1>Resume variants</h1>
        <p>
          One tailored resume per role, grounded in your real resume/projects plus real market
          job data for that role — reused across every job in that role family, unlike a cover
          letter which is generated fresh per job.
        </p>
      </div>

      <section className="card">
        <h2>Create a new variant</h2>
        <form action={createWithProfileId}>
          <div className="field">
            <label htmlFor="role_label">Role</label>
            <input
              id="role_label"
              name="role_label"
              type="text"
              placeholder="e.g. Backend Engineer"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="emphasis_note">Emphasis (optional)</label>
            <span className="field-hint">
              What should this variant emphasize over the rest of your resume?
            </span>
            <textarea id="emphasis_note" name="emphasis_note" rows={3} />
          </div>
          <SubmitButton pendingLabel="Generating…">Generate variant</SubmitButton>
        </form>
      </section>

      {variants.length === 0 ? (
        <p className="empty-state">No resume variants yet.</p>
      ) : (
        variants.map((variant) => (
          <section key={variant.id} className="card">
            <h2>{variant.role_label}</h2>
            {variant.emphasis_note && <p className="field-hint">{variant.emphasis_note}</p>}
            {variant.unverified_claims.length > 0 && (
              <div className="warning-banner">
                <strong>⚠ Unverified — not found in your source resume/projects:</strong>
                <ul>
                  {variant.unverified_claims.map((claim) => (
                    <li key={claim}>{claim}</li>
                  ))}
                </ul>
              </div>
            )}
            <pre>{variant.generated_content}</pre>
          </section>
        ))
      )}
    </main>
  );
}
