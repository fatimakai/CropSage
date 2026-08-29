import { z } from "zod";

const validationCheckSchema = z.object({
  name: z.string().min(1),
  passed: z.boolean(),
  details: z.string().min(1),
});

export const handoffValidationReportSchema = z.object({
  report_version: z.string().min(1),
  sample: z.string().min(1),
  evidence_bundle_id: z.string().min(1),
  profile_id: z.string().min(1),
  scoring_version: z.string().min(1),
  status: z.literal("validated"),
  evidence_bundle_validation: z.object({
    all_passed: z.boolean(),
    coordinate_tolerance_degrees: z.number().positive(),
    invalid_numeric_value_count: z.number().int().min(0),
    checks: z.array(validationCheckSchema).min(1),
    schema_error_count: z.number().int().min(0),
  }),
  engine_output_validation: z.object({
    schema: z.string().min(1),
    passed: z.boolean(),
    ranking_count: z.literal(22),
    unique_crop_count: z.literal(22),
    expected_crop_count: z.literal(22),
    eligible_crop_count: z.number().int().min(0).max(22),
    ineligible_crop_count: z.number().int().min(0).max(22),
    crop_count_valid: z.boolean(),
    unique_crop_count_valid: z.boolean(),
    overall_rank_unique: z.boolean(),
    rank_sequence_valid: z.boolean(),
    eligibility_ordering_valid: z.boolean(),
    within_group_sort_valid: z.boolean(),
    eligible_rank_sequence_valid: z.boolean(),
    ineligible_rank_null_valid: z.boolean(),
    ineligible_suitability_cap_valid: z.boolean(),
    ineligible_recommendation_valid: z.boolean(),
    unsupported_region_gate_valid: z.boolean(),
    eligibility_ranking_policy_passed: z.boolean(),
    schema_error_count: z.number().int().min(0),
    invalid_numeric_value_count: z.number().int().min(0),
  }),
  notes: z.array(z.string()),
});

export const validationGateSchema = z.object({
  outcome: z.enum(["passed", "rejected", "incomplete"]),
  render_allowed: z.boolean(),
  validator_version: z.string().min(1),
  warnings: z.array(z.string()),
  errors: z.array(z.string()),
});

export type HandoffValidationReport = z.infer<typeof handoffValidationReportSchema>;
export type ValidationGate = z.infer<typeof validationGateSchema>;
