import { NextResponse } from "next/server";

import { userOwnsAssessment } from "@/lib/assessments/access";
import {
  getMockProgressSnapshot,
  normalizeProgressStart,
  parseProgressMode,
} from "@/lib/assessments/mock-progress";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { id } = await context.params;

  if (!(await userOwnsAssessment(id))) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "ASSESSMENT_NOT_FOUND",
          message: "This assessment is unavailable for the current session.",
        },
      },
      { status: 404 },
    );
  }

  const url = new URL(request.url);
  const now = Date.now();
  const startedAt = normalizeProgressStart(url.searchParams.get("startedAt"), now);
  const mode = parseProgressMode(url.searchParams.get("mode"));
  const snapshot = getMockProgressSnapshot(id, startedAt, now, mode);

  return NextResponse.json(snapshot, {
    headers: { "cache-control": "no-store" },
  });
}
