import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons";
import { updateProfile } from "@/app/profiles/actions";
import { apiGet, type ProfileOut } from "@/lib/api";
import { ProfileEditForm } from "./profile-edit-form";

export default async function EditProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const profile = await apiGet<ProfileOut>(`/api/v1/profiles/${id}`);

  const updateWithId = updateProfile.bind(null, profile.id);

  return (
    <main>
      <Link href={`/profiles/${id}`} className="breadcrumb-link">
        <ArrowLeftIcon width={15} height={15} />
        Back to profile
      </Link>

      <div className="page-header-text">
        <h1>Edit profile</h1>
        <p>
          Projects aren&apos;t editable here — add or remove those from the profile creation
          flow.
        </p>
      </div>

      <ProfileEditForm profile={profile} action={updateWithId} />
    </main>
  );
}
