import "server-only";

import {
  recommendationOutputSchema,
  validationGateSchema,
  type ValidationGate,
} from "@/lib/contracts";
import {
  prepareRecommendationResult,
  type PreparedRecommendationResult,
} from "@/lib/recommendations/presentation";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";

const unavailableValidation: ValidationGate = {
  outcome: "incomplete",
  render_allowed: false,
  validator_version: "unavailable",
  warnings: [],
  errors: ["A completed, validated recommendation is not available for this assessment."],
};

export async function getPersistedRecommendationResult(
  assessmentSessionId: string,
): Promise<PreparedRecommendationResult> {
  const supabase = createAdminSupabaseClient();
  const { data: run, error: runError } = await supabase
    .from("recommendation_runs")
    .select("id,engine_output_jsonb")
    .eq("assessment_session_id", assessmentSessionId)
    .eq("status", "completed")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (runError || !run?.engine_output_jsonb) {
    return prepareRecommendationResult(
      {} as never,
      unavailableValidation,
    );
  }

  const { data: report, error: reportError } = await supabase
    .from("validation_reports")
    .select("outcome,render_allowed,validator_version,warnings,errors")
    .eq("recommendation_run_id", run.id)
    .maybeSingle();
  if (reportError || !report) {
    return prepareRecommendationResult({} as never, unavailableValidation);
  }

  const recommendation = recommendationOutputSchema.parse(run.engine_output_jsonb);
  const validation = validationGateSchema.parse({
    outcome: report.outcome,
    render_allowed: report.render_allowed,
    validator_version: report.validator_version,
    warnings: report.warnings,
    errors: report.errors,
  });
  return prepareRecommendationResult(recommendation, validation);
}
