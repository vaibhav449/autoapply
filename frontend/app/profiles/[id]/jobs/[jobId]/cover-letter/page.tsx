import Link from "next/link";
import { apiGet, type CoverLetterOut } from "@/lib/api";
import { AlertTriangleIcon, ArrowLeftIcon } from "@/components/icons";

export default async function CoverLetterPage({
  params,
}: {
  params: Promise<{ id: string; jobId: string }>;
}) {
  const { id, jobId } = await params;

  let coverLetter: CoverLetterOut | null = null;
  let error: string | null = null;
  try {
    coverLetter = await apiGet<CoverLetterOut>(`/api/v1/profiles/${id}/jobs/${jobId}/cover-letter`);
  } catch {
    error = "Couldn't generate a cover letter for this job right now — try again in a moment.";
  }

  return (
    <main>
      <Link href={`/profiles/${id}`} className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        Back to profile
      </Link>

      <div className="page-header-text">
        <h1>Cover letter</h1>
      </div>

      {error && (
        <div className="alert alert-info">
          <AlertTriangleIcon className="alert-icon" width={18} height={18} />
          <div className="alert-body">
            <p>{error}</p>
          </div>
        </div>
      )}
      {coverLetter && (
        <section className="card">
          <div className="document document-letter">{coverLetter.content}</div>
        </section>
      )}
    </main>
  );
}
