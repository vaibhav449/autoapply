import Link from "next/link";
import { apiGet, type CoverLetterOut } from "@/lib/api";

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
      <div>
        <Link href={`/profiles/${id}`}>← Back to profile</Link>
      </div>

      <h1>Cover letter</h1>

      {error && <p className="empty-state">{error}</p>}
      {coverLetter && (
        <section className="card">
          <pre>{coverLetter.content}</pre>
        </section>
      )}
    </main>
  );
}
