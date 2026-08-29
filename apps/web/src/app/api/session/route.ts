import { NextResponse } from "next/server";

import { getPublicSupabaseEnvironment } from "@/lib/env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function POST() {
  if (!getPublicSupabaseEnvironment()) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "SUPABASE_NOT_CONFIGURED",
          message: "The application session service is not configured.",
        },
      },
      { status: 503 },
    );
  }

  const supabase = await createServerSupabaseClient();
  const { data: current } = await supabase.auth.getUser();

  if (current.user) {
    return NextResponse.json(
      {
        ok: true,
        userId: current.user.id,
        isAnonymous: current.user.is_anonymous ?? false,
      },
      { headers: { "cache-control": "no-store" } },
    );
  }

  const { data, error } = await supabase.auth.signInAnonymously();

  if (error || !data.user) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "ANONYMOUS_SESSION_FAILED",
          message: "A private assessment session could not be started.",
        },
      },
      { status: 503 },
    );
  }

  return NextResponse.json(
    {
      ok: true,
      userId: data.user.id,
      isAnonymous: data.user.is_anonymous ?? true,
    },
    { headers: { "cache-control": "no-store" } },
  );
}
