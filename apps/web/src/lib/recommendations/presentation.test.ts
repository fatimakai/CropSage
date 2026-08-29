import { describe, expect, it } from "vitest";

import correctedEngineOutput from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";
import correctedValidationReport from "../../../../../handoff/fatima_scoring_migrations/sample_validation_report.json";

import {
  handoffValidationReportSchema,
  recommendationOutputSchema,
} from "@/lib/contracts";
import {
  buildFixtureValidationGate,
  formatScore,
  groupRecommendationRankings,
  prepareRecommendationResult,
} from "@/lib/recommendations/presentation";

const recommendation = recommendationOutputSchema.parse(correctedEngineOutput);
const report = handoffValidationReportSchema.parse(correctedValidationReport);

describe("recommendation presentation", () => {
  it("accepts the corrected fixture and preserves both ranking groups", () => {
    const validation = buildFixtureValidationGate(report, recommendation);
    const groups = groupRecommendationRankings(recommendation.rankings);

    expect(validation).toMatchObject({ outcome: "passed", render_allowed: true });
    expect(groups.topThree.map((crop) => crop.crop_id)).toEqual([
      "alfalfa_hay",
      "fresh_market_spinach",
      "oilseed_sunflower",
    ]);
    expect(groups.eligible).toHaveLength(21);
    expect(groups.eligible.map((crop) => crop.eligible_rank)).toEqual(
      Array.from({ length: 21 }, (_, index) => index + 1),
    );
    expect(groups.ineligible).toHaveLength(1);
    expect(groups.ineligible[0]).toMatchObject({
      crop_id: "long_grain_rice",
      overall_rank: 22,
      eligible_rank: null,
    });
  });

  it("hides recommendation data whenever validation does not allow rendering", () => {
    const result = prepareRecommendationResult(recommendation, {
      outcome: "rejected",
      render_allowed: false,
      validator_version: "test-validator",
      warnings: [],
      errors: ["Ranking validation failed."],
    });

    expect(result).toEqual({
      state: "blocked",
      validation: expect.objectContaining({ render_allowed: false }),
    });
    expect("recommendation" in result).toBe(false);
  });

  it("rejects a validator report for a different recommendation artifact", () => {
    const mismatchedReport = {
      ...report,
      profile_id: "another_profile",
    };

    expect(buildFixtureValidationGate(mismatchedReport, recommendation)).toMatchObject({
      outcome: "rejected",
      render_allowed: false,
      errors: ["The validator report does not describe this recommendation artifact."],
    });
  });

  it("renders absent numeric evidence as unknown rather than zero", () => {
    expect(formatScore(null)).toBe("Unknown");
    expect(formatScore(0)).toBe("0.0");
  });
});
