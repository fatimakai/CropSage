import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogFixture from "../../../../../data/crop-catalog/catalog.json";
import evidenceFixture from "../../../../../handoff/fatima_scoring_migrations/sample_evidence_bundle.json";
import engineOutputFixture from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";

import { recommendationOutputSchema } from "@/lib/contracts";
import { getPersistedRecommendationContext } from "@/lib/recommendations/persisted-results";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/recommendations/persisted-results", () => ({
  getPersistedRecommendationContext: vi.fn(),
}));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminSupabaseClient: vi.fn(),
}));

import { getPersistedCropDetail } from "@/lib/crops/prepared-crop-details";

const validation = {
  outcome: "passed" as const,
  render_allowed: true,
  validator_version: "test-validator",
  warnings: [],
  errors: [],
};

describe("persisted crop details", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the crop score and EvidenceBundle linked to the requested assessment", async () => {
    const recommendation = recommendationOutputSchema.parse(
      structuredClone(engineOutputFixture),
    );
    const crop = recommendation.rankings.find(
      (ranking) => ranking.crop_id === "alfalfa_hay",
    );
    expect(crop).toBeDefined();
    crop!.suitability_score = 42.75;
    recommendation.location.farm_name = "Current farmer field";
    recommendation.location.texas_region_id = "plains";

    vi.mocked(getPersistedRecommendationContext).mockResolvedValue({
      result: { state: "ready", recommendation, validation },
      recommendationRunId: "run-current",
      evidenceBundleId: "bundle-current",
    });

    const maybeSingle = vi.fn().mockResolvedValue({
      data: { bundle_snapshot: evidenceFixture },
      error: null,
    });
    const statusFilter = vi.fn(() => ({ maybeSingle }));
    const idFilter = vi.fn(() => ({ eq: statusFilter }));
    const select = vi.fn(() => ({ eq: idFilter }));
    const from = vi.fn(() => ({ select }));
    vi.mocked(createAdminSupabaseClient).mockReturnValue({ from } as never);

    const detail = await getPersistedCropDetail(
      "assessment-current",
      "alfalfa_hay",
    );

    expect(getPersistedRecommendationContext).toHaveBeenCalledWith(
      "assessment-current",
    );
    expect(from).toHaveBeenCalledWith("evidence_bundles");
    expect(idFilter).toHaveBeenCalledWith("id", "bundle-current");
    expect(statusFilter).toHaveBeenCalledWith("status", "validated");
    expect(detail.state).toBe("ready");
    if (detail.state !== "ready") return;

    expect(detail.crop.suitability_score).toBe(42.75);
    expect(detail.location).toEqual({
      farmName: "Current farmer field",
      texasRegionId: "plains",
    });
    expect(detail.providers).toHaveLength(4);
    expect(detail.catalog.crop_id).toBe(
      catalogFixture.crops.find((item) => item.crop_id === "alfalfa_hay")?.crop_id,
    );
  });
});
