import { AppShell } from "@/components/app-shell";
import { FarmProfileForm } from "@/components/farm-profile/farm-profile-form";

export const dynamic = "force-dynamic";

export default function FarmSetupPage() {
  return (
    <AppShell>
      <FarmProfileForm />
    </AppShell>
  );
}
