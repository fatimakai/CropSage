import { NextResponse } from "next/server";

import { userOwnsAssessment } from "@/lib/assessments/access";
import { executeAssessment } from "@/lib/assessments/execution";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
export const runtime = "nodejs";

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  if (!(await userOwnsAssessment(id))) {
    return NextResponse.json(
      { ok: false, error: { code: "ASSESSMENT_NOT_FOUND", message: "Assessment unavailable." } },
      { status: 404 },
    );
  }

  try {
    const result = await executeAssessment(id);
    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    console.error("assessment_execution_failed", {
      assessmentSessionId: id,
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "ASSESSMENT_EXECUTION_FAILED",
          message: "The assessment could not be completed. Please try again.",
        },
      },
      { status: 502 },
    );
  }
}
