import { describe, expect, it } from "vitest";

import correctedEngineOutput from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";

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
    const result = recommendationOutputSchema.safeParse(correctedEngineOutput);

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
