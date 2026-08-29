import type {
  CropScoreResult,
  HandoffValidationReport,
  RecommendationOutput,
  ValidationGate,
} from "@/lib/contracts";

export type ReadyRecommendationResult = {
  state: "ready";
  recommendation: RecommendationOutput;
  validation: ValidationGate;
};

export type BlockedRecommendationResult = {
  state: "blocked";
  validation: ValidationGate;
};

export type PreparedRecommendationResult =
  | ReadyRecommendationResult
  | BlockedRecommendationResult;

const requiredEngineChecks = [
  "crop_count_valid",
  "unique_crop_count_valid",
  "overall_rank_unique",
  "rank_sequence_valid",
  "eligibility_ordering_valid",
  "within_group_sort_valid",
  "eligible_rank_sequence_valid",
  "ineligible_rank_null_valid",
  "ineligible_suitability_cap_valid",
  "ineligible_recommendation_valid",
  "unsupported_region_gate_valid",
  "eligibility_ranking_policy_passed",
] as const;

export function buildFixtureValidationGate(
  report: HandoffValidationReport,
  recommendation: RecommendationOutput,
): ValidationGate {
  const errors: string[] = [];
  const engineValidation = report.engine_output_validation;
  const eligibleCount = recommendation.rankings.filter(
    (crop) => crop.regionally_eligible,
  ).length;

  if (!report.evidence_bundle_validation.all_passed) {
    errors.push("The evidence bundle did not pass every required validation check.");
  }
  if (!engineValidation.passed) {
    errors.push("The deterministic engine output did not pass validation.");
  }
  if (requiredEngineChecks.some((check) => !engineValidation[check])) {
    errors.push("At least one ranking or eligibility contract check failed.");
  }
  if (
    report.evidence_bundle_validation.schema_error_count > 0 ||
    engineValidation.schema_error_count > 0
  ) {
    errors.push("A handoff artifact contains schema errors.");
  }
  if (
    report.evidence_bundle_validation.invalid_numeric_value_count > 0 ||
    engineValidation.invalid_numeric_value_count > 0
  ) {
    errors.push("A handoff artifact contains an invalid numeric value.");
  }
  if (
    report.profile_id !== recommendation.profile_id ||
    report.evidence_bundle_id !== recommendation.evidence_bundle_id ||
    report.scoring_version !== recommendation.scoring_version
  ) {
    errors.push("The validator report does not describe this recommendation artifact.");
  }
  if (
    engineValidation.eligible_crop_count !== eligibleCount ||
    engineValidation.ineligible_crop_count !== recommendation.rankings.length - eligibleCount
  ) {
    errors.push("The validator crop counts do not match the recommendation artifact.");
  }

  return {
    outcome: errors.length === 0 ? "passed" : "rejected",
    render_allowed: errors.length === 0,
    validator_version: `handoff-validator-${report.report_version}`,
    warnings: report.notes,
    errors,
  };
}

export function prepareRecommendationResult(
  recommendation: RecommendationOutput,
  validation: ValidationGate,
): PreparedRecommendationResult {
  if (validation.outcome !== "passed" || !validation.render_allowed) {
    return { state: "blocked", validation };
  }

  return { state: "ready", recommendation, validation };
}

export function groupRecommendationRankings(rankings: CropScoreResult[]) {
  const eligible = rankings
    .filter((crop) => crop.regionally_eligible)
    .sort((left, right) => (left.eligible_rank ?? 99) - (right.eligible_rank ?? 99));
  const ineligible = rankings
    .filter((crop) => !crop.regionally_eligible)
    .sort((left, right) => left.overall_rank - right.overall_rank);

  return {
    topThree: eligible.slice(0, 3),
    eligible,
    ineligible,
  };
}

export function formatScore(value: number | null) {
  return value === null ? "Unknown" : value.toFixed(1);
}

export function titleCaseIdentifier(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
