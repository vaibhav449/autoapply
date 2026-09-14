import { createProfile } from "@/app/profiles/actions";
import { ProfileForm } from "./profile-form";

export default function NewProfilePage() {
  return (
    <main>
      <h1>Create your master profile</h1>
      <p>Your resume, in-depth project write-ups, and preferences — used to find and rank matching jobs.</p>
      <ProfileForm action={createProfile} />
    </main>
  );
}
