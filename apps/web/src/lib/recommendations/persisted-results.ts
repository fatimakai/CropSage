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

export type PersistedRecommendationContext = {
  result: PreparedRecommendationResult;
  recommendationRunId: string | null;
  evidenceBundleId: string | null;
};

export async function getPersistedRecommendationContext(
  assessmentSessionId: string,
): Promise<PersistedRecommendationContext> {
  const supabase = createAdminSupabaseClient();
  const { data: run, error: runError } = await supabase
    .from("recommendation_runs")
    .select("id,evidence_bundle_id,engine_output_jsonb")
    .eq("assessment_session_id", assessmentSessionId)
    .eq("status", "completed")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (runError || !run?.engine_output_jsonb) {
    return {
      result: prepareRecommendationResult({} as never, unavailableValidation),
      recommendationRunId: null,
      evidenceBundleId: null,
    };
  }

  const { data: report, error: reportError } = await supabase
    .from("validation_reports")
    .select("outcome,render_allowed,validator_version,warnings,errors")
    .eq("recommendation_run_id", run.id)
    .maybeSingle();
  if (reportError || !report) {
    return {
      result: prepareRecommendationResult({} as never, unavailableValidation),
      recommendationRunId: run.id,
      evidenceBundleId: run.evidence_bundle_id,
    };
  }

  const recommendation = recommendationOutputSchema.parse(run.engine_output_jsonb);
  const validation = validationGateSchema.parse({
    outcome: report.outcome,
    render_allowed: report.render_allowed,
    validator_version: report.validator_version,
    warnings: report.warnings,
    errors: report.errors,
  });
  return {
    result: prepareRecommendationResult(recommendation, validation),
    recommendationRunId: run.id,
    evidenceBundleId: run.evidence_bundle_id,
  };
}

export async function getPersistedRecommendationResult(
  assessmentSessionId: string,
): Promise<PreparedRecommendationResult> {
  return (await getPersistedRecommendationContext(assessmentSessionId)).result;
}
