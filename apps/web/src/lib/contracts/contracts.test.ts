import { describe, expect, it } from "vitest";

import {
  farmProfileDraftSchema,
  progressEventSchema,
  recommendationOutputSchema,
  sessionBootstrapResponseSchema,
} from "@/lib/contracts";

describe("frontend contracts", () => {
  it("accepts a minimal Texas farm profile with an explicit planting month", () => {
    const result = farmProfileDraftSchema.safeParse({
      location: {
        latitude: 34.18,
        longitude: -101.76,
        source: "demo_farm",
        farm_name: "Plainview demonstration farm",
      },
      planting: {
        planned_month: "2026-08",
        flexibility_days: 30,
      },
      irrigation: {
        availability: "yes",
        reliability: "reliable",
      },
    });

    expect(result.success).toBe(true);
  });

  it("rejects a planting plan that supplies both date and month", () => {
    const result = farmProfileDraftSchema.safeParse({
      location: {
        latitude: 34.18,
        longitude: -101.76,
        source: "manual_coordinates",
      },
      planting: {
        planned_date: "2026-08-15",
        planned_month: "2026-08",
      },
    });

    expect(result.success).toBe(false);
  });

  it("accepts only user-safe progress event shapes", () => {
    expect(
      progressEventSchema.safeParse({
        sequenceNumber: 1,
        kind: "provider",
        name: "provider.nasa_power.started",
        status: "started",
        safeSummary: "Regional climate evidence is being collected.",
        occurredAt: "2026-08-29T10:00:00Z",
      }).success,
    ).toBe(true);
  });

  it("requires all 22 corrected eligibility-aware ranking rows", () => {
    const rankings = Array.from({ length: 22 }, (_, index) => ({
      crop_id: `crop_${String(index + 1).padStart(2, "0")}`,
      crop_name: `Crop ${index + 1}`,
      status: "scored",
      regionally_eligible: index < 21,
      overall_rank: index + 1,
      eligible_rank: index < 21 ? index + 1 : null,
      suitability_score: index < 21 ? 90 - index : 54,
      recommendation: index < 21 ? "recommended" : "not_recommended",
      confidence_score: 80,
      confidence_band: "high",
      evidence_coverage_percent: 100,
      factors: [],
    }));

    const result = recommendationOutputSchema.safeParse({
      schema_version: "1.1.0",
      scoring_version: "1.0.0-provisional",
      status: "validated",
      evaluation_mode: "planning",
      profile_id: "plainview_demo",
      evidence_bundle_id: "plainview_evidence",
      rankings,
    });

    expect(result.success).toBe(true);
  });

  it("validates successful anonymous session responses", () => {
    expect(
      sessionBootstrapResponseSchema.safeParse({
        ok: true,
        userId: "76000000-0000-4000-8000-000000000001",
        isAnonymous: true,
      }).success,
    ).toBe(true);
  });
});
