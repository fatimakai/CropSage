import { NextResponse } from "next/server";

import { userOwnsAssessment } from "@/lib/assessments/access";
import {
  getMockProgressSchedule,
  normalizeProgressStart,
  parseProgressMode,
} from "@/lib/assessments/mock-progress";
import { progressEventSchema } from "@/lib/contracts";

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

  const url = new URL(request.url);
  const startedAt = normalizeProgressStart(url.searchParams.get("startedAt"));
  const mode = parseProgressMode(url.searchParams.get("mode"));
  const schedule = getMockProgressSchedule(mode);
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let cancelled = false;

      request.signal.addEventListener("abort", () => {
        cancelled = true;
      });

      async function sendEvents() {
        controller.enqueue(encoder.encode("retry: 1500\n\n"));

        for (const scheduled of schedule) {
          const waitMs = Math.max(0, startedAt + scheduled.offsetMs - Date.now());
          if (waitMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, waitMs));
          }
          if (cancelled) return;

          const event = progressEventSchema.parse({
            ...scheduled.event,
            occurredAt: new Date(startedAt + scheduled.offsetMs).toISOString(),
          });
          controller.enqueue(
            encoder.encode(`event: progress\ndata: ${JSON.stringify(event)}\n\n`),
          );
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
