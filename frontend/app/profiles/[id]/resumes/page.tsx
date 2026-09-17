import Link from "next/link";
import { API_BASE_URL, apiGet, type ResumeVariantOut } from "@/lib/api";
import { createResumeVariant } from "@/app/profiles/actions";
import { SubmitButton } from "@/components/submit-button";
import { AlertTriangleIcon, ArrowLeftIcon, DownloadIcon, FileTextIcon } from "@/components/icons";

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
      <Link href={`/profiles/${id}`} className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        Back to profile
      </Link>

      <div className="page-header-text">
        <h1>Resume variants</h1>
        <p>
          One tailored resume per role, grounded in your real resume/projects plus real market
          job data for that role — reused across every job in that role family, unlike a cover
          letter which is generated fresh per job.
        </p>
      </div>

      <section className="card">
        <div className="card-head">
          <div className="card-head-text">
            <h2>Create a new variant</h2>
          </div>
        </div>
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
        <div className="empty-panel">
          <span className="empty-panel-icon">
            <FileTextIcon width={22} height={22} />
          </span>
          <h2>No resume variants yet</h2>
          <p>Generate one above to get a role-tailored resume ready to download as a PDF.</p>
        </div>
      ) : (
        variants.map((variant) => (
          <section key={variant.id} className="card">
            <div className="card-head">
              <div className="card-head-text">
                <h2>{variant.role_label}</h2>
                {variant.emphasis_note && <p className="text-muted text-small">{variant.emphasis_note}</p>}
              </div>
              <a
                className="btn btn-secondary"
                href={`${API_BASE_URL}/api/v1/profiles/${id}/resume-variants/${variant.id}/pdf`}
                target="_blank"
                rel="noreferrer"
              >
                <DownloadIcon width={16} height={16} />
                Download PDF
              </a>
            </div>
            {variant.unverified_claims.length > 0 && (
              <div className="alert alert-warning">
                <AlertTriangleIcon className="alert-icon" width={18} height={18} />
                <div className="alert-body">
                  <strong>Unverified — not found in your source resume/projects</strong>
                  <ul>
                    {variant.unverified_claims.map((claim) => (
                      <li key={claim}>{claim}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            <div className="document">{variant.generated_content}</div>
          </section>
        ))
      )}
    </main>
  );
}
