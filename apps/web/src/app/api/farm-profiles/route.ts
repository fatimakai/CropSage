import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";

import { farmProfileDraftSchema } from "@/lib/contracts";
import { buildFarmProfileSnapshot, getMissingFarmProfileFields } from "@/lib/farm-profile/snapshot";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const parsed = farmProfileDraftSchema.safeParse(await request.json().catch(() => null));

  if (!parsed.success) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "INVALID_FARM_PROFILE",
          message: parsed.error.issues[0]?.message ?? "The farm profile is invalid.",
        },
      },
      { status: 400 },
    );
  }

  const supabase = await createServerSupabaseClient();
  let { data: current } = await supabase.auth.getUser();

  if (!current.user) {
    const { data, error } = await supabase.auth.signInAnonymously();
    if (error || !data.user) {
      return NextResponse.json(
        {
          ok: false,
          error: {
            code: "SESSION_REQUIRED",
            message: "A private assessment session could not be started.",
          },
        },
        { status: 401 },
      );
    }
    current = { user: data.user };
  }

  const profileId = `profile_${randomUUID().replaceAll("-", "")}`;
  const snapshot = buildFarmProfileSnapshot(parsed.data, {
    profileId,
    capturedAt: new Date().toISOString(),
  });
  const missingFields = getMissingFarmProfileFields(parsed.data);
  const completenessNotes = missingFields.length
    ? ["Optional farm evidence was not supplied; unavailable values must lower confidence, not count as matches."]
    : [];

  const admin = createAdminSupabaseClient();
  const { data, error } = await admin.rpc("create_farm_profile", {
    p_owner_user_id: current.user.id,
    p_profile_snapshot: snapshot,
    p_missing_fields: missingFields,
    p_completeness_notes: completenessNotes,
  });
  const saved = Array.isArray(data) ? data[0] : null;

  if (error || !saved) {
    console.error("Farm profile intake failed", {
      code: error?.code,
      message: error?.message,
    });
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "FARM_PROFILE_SAVE_FAILED",
          message: "The farm profile could not be saved. Please try again.",
        },
      },
      { status: 503 },
    );
  }

  return NextResponse.json(
    {
      ok: true,
      assessmentSessionId: saved.assessment_session_id,
      farmProfileId: saved.farm_profile_id,
      externalProfileId: saved.external_profile_id,
    },
    { status: 201, headers: { "cache-control": "no-store" } },
  );
}
