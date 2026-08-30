import { NextResponse } from "next/server";

import { userOwnsAssessment } from "@/lib/assessments/access";
import { getAssessmentProgress } from "@/lib/assessments/runtime";

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

  const snapshot = await getAssessmentProgress(id);

  return NextResponse.json(snapshot, {
    headers: { "cache-control": "no-store" },
  });
}
