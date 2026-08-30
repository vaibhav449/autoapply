import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>AutoApply</h1>
      <ul>
        <li>
          <Link href="/applications">Applications</Link>
        </li>
        <li>
          <Link href="/review">Review</Link>
        </li>
        <li>
          <Link href="/pending">Pending</Link>
        </li>
        <li>
          <Link href="/analytics">Analytics</Link>
        </li>
      </ul>
    </main>
  );
}
