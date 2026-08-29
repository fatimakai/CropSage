import { z } from "zod";

export const recommendationClassSchema = z.enum([
  "recommended",
  "conditional",
  "not_recommended",
  "insufficient_evidence",
]);

export const confidenceBandSchema = z.enum(["high", "medium", "low"]);

export const scoreExplanationSchema = z.object({
  factor_id: z.string().min(1),
  score: z.number().min(0).max(100),
  reason: z.string().min(1),
});

export const scoreGateSchema = z.object({
  gate: z.string().min(1),
  cap: z.number().min(0).max(100),
  reason: z.string().min(1),
});

export const scoreFactorSchema = z.object({
  factor_id: z.string().min(1),
  category: z.string().min(1),
  weight_percent: z.number().min(0).max(100),
  available: z.boolean(),
  score: z.number().min(0).max(100).nullable(),
  evidence_confidence: z.number().min(0).max(1),
  weighted_points: z.number().min(0).max(100).nullable(),
  scoring_use: z.enum(["scored", "informational_only", "inactive"]),
  reason: z.string().min(1),
  evidence: z.object({
    sources: z.array(z.string()),
    values: z.record(z.string(), z.unknown()),
  }),
});

export const cropScoreResultSchema = z
  .object({
    crop_id: z.string().regex(/^[a-z0-9][a-z0-9_]*$/),
    crop_name: z.string().min(1).max(160),
    status: z.enum(["scored", "insufficient_evidence"]),
    regionally_eligible: z.boolean(),
    overall_rank: z.number().int().min(1).max(22),
    eligible_rank: z.number().int().min(1).max(22).nullable(),
    suitability_score: z.number().min(0).max(100).nullable(),
    recommendation: recommendationClassSchema,
    confidence_score: z.number().min(0).max(100).nullable(),
    confidence_band: confidenceBandSchema.nullable(),
    evidence_coverage_percent: z.number().min(0).max(100).nullable(),
    applied_caps: z.array(scoreGateSchema).default([]),
    applied_gates: z.array(scoreGateSchema).default([]),
    factors: z.array(scoreFactorSchema),
    key_strengths: z.array(scoreExplanationSchema).default([]),
    key_risks: z.array(scoreExplanationSchema).default([]),
    warnings: z.array(z.string()).default([]),
  })
  .superRefine((result, context) => {
    if (result.regionally_eligible && result.eligible_rank === null) {
      context.addIssue({
        code: "custom",
        path: ["eligible_rank"],
        message: "Eligible crops require an eligible rank.",
      });
    }

    if (!result.regionally_eligible && result.eligible_rank !== null) {
      context.addIssue({
        code: "custom",
        path: ["eligible_rank"],
        message: "Ineligible crops cannot have an eligible rank.",
      });
    }
  });

export const recommendationOutputSchema = z
  .object({
    schema_version: z.string().min(1),
    scoring_version: z.string().min(1),
    generated_at: z.iso.datetime({ offset: true }),
    status: z.literal("validated"),
    evaluation_mode: z.enum(["planning", "planting_readiness"]),
    profile_id: z.string().min(1),
    evidence_bundle_id: z.string().min(1),
    location: z.object({
      farm_id: z.string().min(1),
      farm_name: z.string().min(1),
      latitude: z.number().min(25.84).max(36.5),
      longitude: z.number().min(-106.65).max(-93.5),
      texas_region_id: z.string().min(1),
      timezone: z.string().min(1),
    }),
    requested_crop_id: z.string().nullable(),
    requested_crop_result: cropScoreResultSchema.nullable(),
    rankings: z.array(cropScoreResultSchema).length(22),
    limitations: z.array(z.string()).default([]),
    method: z.object({
      suitability: z.string().min(1),
      confidence: z.string().min(1),
      active_weight_percent: z.number().min(0).max(100),
    }),
  })
  .superRefine((output, context) => {
    const overallRanks = output.rankings.map((crop) => crop.overall_rank);
    const eligibleRanks = output.rankings
      .filter((crop) => crop.regionally_eligible)
      .map((crop) => crop.eligible_rank);
    const expectedOverallRanks = Array.from({ length: 22 }, (_, index) => index + 1);
    const expectedEligibleRanks = Array.from(
      { length: eligibleRanks.length },
      (_, index) => index + 1,
    );

    if (new Set(output.rankings.map((crop) => crop.crop_id)).size !== 22) {
      context.addIssue({
        code: "custom",
        path: ["rankings"],
        message: "All crop IDs in a recommendation must be unique.",
      });
    }

    if (JSON.stringify(overallRanks) !== JSON.stringify(expectedOverallRanks)) {
      context.addIssue({
        code: "custom",
        path: ["rankings"],
        message: "Overall ranks must be ordered from 1 through 22.",
      });
    }

    if (JSON.stringify(eligibleRanks) !== JSON.stringify(expectedEligibleRanks)) {
      context.addIssue({
        code: "custom",
        path: ["rankings"],
        message: "Eligible ranks must be ordered and contiguous.",
      });
    }
  });

export const scoringRequestSchema = z.object({
  farm_profile: z.record(z.string(), z.unknown()),
  evidence_bundle: z.record(z.string(), z.unknown()),
  scoring_config: z.record(z.string(), z.unknown()),
});

export type CropScoreResult = z.infer<typeof cropScoreResultSchema>;
export type RecommendationOutput = z.infer<typeof recommendationOutputSchema>;
export type ScoreExplanation = z.infer<typeof scoreExplanationSchema>;
export type ScoreFactor = z.infer<typeof scoreFactorSchema>;
export type ScoringRequest = z.infer<typeof scoringRequestSchema>;
