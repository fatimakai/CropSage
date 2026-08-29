import { NextResponse } from "next/server";

import {
  getPublicSupabaseEnvironment,
  getScoringApiUrl,
  getServerSupabaseEnvironment,
} from "@/lib/env";

export function GET() {
  return NextResponse.json(
    {
      status: "ok",
      services: {
        web: "ready",
        supabase: getPublicSupabaseEnvironment() ? "configured" : "not_configured",
        profileIntake: getServerSupabaseEnvironment() ? "configured" : "not_configured",
        scoringEngine: getScoringApiUrl() ? "configured" : "not_configured",
      },
    },
    { headers: { "cache-control": "no-store" } },
  );
}
