import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>AutoApply</h1>
      <p>Build a master profile once, and get ranked, personalized job matches automatically.</p>
      <div>
        <Link href="/profiles/new" className="btn">
          Create your profile
        </Link>
      </div>
    </main>
  );
}
