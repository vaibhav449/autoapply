import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons";
import { createProfile } from "@/app/profiles/actions";
import { ProfileForm } from "./profile-form";

export default function NewProfilePage() {
  return (
    <main>
      <Link href="/profiles" className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        All profiles
      </Link>

      <div className="page-header-text">
        <h1>Create your master profile</h1>
        <p>Your resume, in-depth project write-ups, and preferences — used to find and rank matching jobs.</p>
      </div>

      <ProfileForm action={createProfile} />
    </main>
  );
}
