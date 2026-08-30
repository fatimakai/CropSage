import { NextResponse } from "next/server";

import { userOwnsAssessment } from "@/lib/assessments/access";
import { getAssessmentProgress } from "@/lib/assessments/runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

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

  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let cancelled = false;

      request.signal.addEventListener("abort", () => {
        cancelled = true;
      });

      async function sendEvents() {
        let lastSequence = 0;
        const deadline = Date.now() + 25_000;
        controller.enqueue(encoder.encode("retry: 1500\n\n"));

        while (!cancelled && Date.now() < deadline) {
          const snapshot = await getAssessmentProgress(id);
          for (const event of snapshot.events.filter(
            (candidate) => candidate.sequenceNumber > lastSequence,
          )) {
            lastSequence = event.sequenceNumber;
            controller.enqueue(
              encoder.encode(`event: progress\ndata: ${JSON.stringify(event)}\n\n`),
            );
          }
          if (snapshot.terminal) break;
          await new Promise((resolve) => setTimeout(resolve, 750));
        }

        if (!cancelled) controller.close();
      }

      void sendEvents().catch((error: unknown) => {
        if (!cancelled) controller.error(error);
      });
    },
  });

  return new Response(stream, {
    headers: {
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "content-type": "text/event-stream; charset=utf-8",
      "x-accel-buffering": "no",
    },
  });
}
