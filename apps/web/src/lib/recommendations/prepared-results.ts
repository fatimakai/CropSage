import "server-only";

import engineOutputFixture from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";
import validationReportFixture from "../../../../../handoff/fatima_scoring_migrations/sample_validation_report.json";

import {
  handoffValidationReportSchema,
  recommendationOutputSchema,
  type ValidationGate,
} from "@/lib/contracts";
import {
  buildFixtureValidationGate,
  prepareRecommendationResult,
  type PreparedRecommendationResult,
} from "@/lib/recommendations/presentation";

type PreparedResultOptions = {
  previewBlocked?: boolean;
};

export function getPreparedRecommendationResult(
  options: PreparedResultOptions = {},
): PreparedRecommendationResult {
  const recommendation = recommendationOutputSchema.parse(engineOutputFixture);
  const report = handoffValidationReportSchema.parse(validationReportFixture);
  let validation = buildFixtureValidationGate(report, recommendation);

  if (options.previewBlocked) {
    validation = {
      ...validation,
      outcome: "incomplete",
      render_allowed: false,
      errors: ["Result validation has not authorized this recommendation for display."],
    } satisfies ValidationGate;
  }

  return prepareRecommendationResult(recommendation, validation);
}
