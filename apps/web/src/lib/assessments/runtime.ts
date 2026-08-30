import "server-only";

import { analysisProgressSnapshotSchema, type AnalysisProgressSnapshot } from "@/lib/contracts";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";

type RunEventRow = {
  sequence_number: number;
  event_kind: "provider" | "evidence" | "scoring" | "validation" | "system";
  event_name: string;
  status: "started" | "succeeded" | "failed" | "info";
  safe_summary: string;
  cache_state: "live" | "cache" | "fallback" | null;
  occurred_at: string;
};

export async function getAssessmentProgress(
  assessmentSessionId: string,
): Promise<AnalysisProgressSnapshot> {
  const supabase = createAdminSupabaseClient();
  const { data: run, error: runError } = await supabase
    .from("recommendation_runs")
    .select("id,status")
    .eq("assessment_session_id", assessmentSessionId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (runError) throw runError;
  if (!run) {
    return analysisProgressSnapshotSchema.parse({
      assessmentSessionId,
      status: "running",
      outcome: null,
      terminal: false,
      events: [],
    });
  }

  const { data: rows, error: eventsError } = await supabase
    .from("run_events")
    .select("sequence_number,event_kind,event_name,status,safe_summary,cache_state,occurred_at")
    .eq("recommendation_run_id", run.id)
    .order("sequence_number", { ascending: true });
  if (eventsError) throw eventsError;

  const events = ((rows ?? []) as RunEventRow[]).map((event) => ({
    sequenceNumber: event.sequence_number,
    kind: event.event_kind,
    name: event.event_name,
    status: event.status,
    safeSummary: event.safe_summary,
    cacheState: event.cache_state,
    occurredAt: event.occurred_at,
  }));
  const failed = run.status === "failed";
  const completed = run.status === "completed";
  const usedFallback = events.some((event) => event.cacheState === "fallback");

  return analysisProgressSnapshotSchema.parse({
    assessmentSessionId,
    status: failed ? "failed" : completed ? "completed" : "running",
    outcome: failed ? "failure" : completed ? (usedFallback ? "fallback" : "success") : null,
    terminal: failed || completed,
    events,
  });
}
