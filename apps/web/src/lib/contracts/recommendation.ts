import { z } from "zod";

export const recommendationClassSchema = z.enum([
  "recommended",
  "conditional",
  "not_recommended",
  "insufficient_evidence",
]);

export const confidenceBandSchema = z.enum(["high", "medium", "low"]);

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
    applied_caps: z.array(z.unknown()).default([]),
    applied_gates: z.array(z.unknown()).default([]),
    factors: z.array(z.unknown()),
    key_strengths: z.array(z.unknown()).default([]),
    key_risks: z.array(z.unknown()).default([]),
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

export const recommendationOutputSchema = z.object({
  schema_version: z.string().min(1),
  scoring_version: z.string().min(1),
  status: z.string().min(1),
  evaluation_mode: z.enum(["planning", "planting_readiness"]),
  profile_id: z.string().min(1),
  evidence_bundle_id: z.string().min(1),
  requested_crop_id: z.string().nullable().optional(),
  rankings: z.array(cropScoreResultSchema).length(22),
  limitations: z.array(z.string()).default([]),
});

export const scoringRequestSchema = z.object({
  farm_profile: z.record(z.string(), z.unknown()),
  evidence_bundle: z.record(z.string(), z.unknown()),
  scoring_config: z.record(z.string(), z.unknown()),
});

export type CropScoreResult = z.infer<typeof cropScoreResultSchema>;
export type RecommendationOutput = z.infer<typeof recommendationOutputSchema>;
export type ScoringRequest = z.infer<typeof scoringRequestSchema>;
