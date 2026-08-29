import { describe, expect, it } from "vitest";

import catalogFixture from "../../../../../data/crop-catalog/catalog.json";
import engineOutputFixture from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";
import evidenceFixture from "../../../../../handoff/fatima_scoring_migrations/sample_evidence_bundle.json";

import {
  cropCatalogSchema,
  evidenceDetailBundleSchema,
  recommendationOutputSchema,
} from "@/lib/contracts";
import { buildRequirementComparisons } from "@/lib/crops/presentation";

describe("prepared crop details", () => {
  it("accepts the 22-crop catalog and four-provider provenance fixture", () => {
    const catalog = cropCatalogSchema.parse(catalogFixture);
    const evidence = evidenceDetailBundleSchema.parse(evidenceFixture);

    expect(catalog.crops).toHaveLength(22);
    expect(Object.keys(evidence.provenance)).toEqual([
      "fortyguard",
      "nasa_power",
      "open_meteo",
      "ssurgo",
    ]);
  });

  it("builds requirement comparisons only from catalog and engine evidence", () => {
    const catalog = cropCatalogSchema.parse(catalogFixture);
    const recommendation = recommendationOutputSchema.parse(engineOutputFixture);
    const crop = recommendation.rankings.find((item) => item.crop_id === "alfalfa_hay");
    const catalogCrop = catalog.crops.find((item) => item.crop_id === "alfalfa_hay");

    expect(crop).toBeDefined();
    expect(catalogCrop).toBeDefined();
    const rows = buildRequirementComparisons(crop!, catalogCrop!);

    expect(rows).toHaveLength(9);
    expect(rows.find((row) => row.id === "soil_ph")).toMatchObject({
      catalogValue: "6.3-7.5",
      locationValue: "7.7",
      factorScore: 75,
    });
    expect(rows.find((row) => row.id === "planting_window")?.locationValue).toBe(
      "Requested month 8",
    );
  });

  it("keeps catalog and recommendation crop IDs aligned for every detail route", () => {
    const catalog = cropCatalogSchema.parse(catalogFixture);
    const recommendation = recommendationOutputSchema.parse(engineOutputFixture);
    const catalogById = new Map(catalog.crops.map((crop) => [crop.crop_id, crop]));

    expect(new Set(catalogById.keys())).toEqual(
      new Set(recommendation.rankings.map((crop) => crop.crop_id)),
    );
    for (const crop of recommendation.rankings) {
      expect(buildRequirementComparisons(crop, catalogById.get(crop.crop_id)!)).toHaveLength(9);
    }
  });
});
