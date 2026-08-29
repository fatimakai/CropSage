import "server-only";

import catalogFixture from "../../../../../data/crop-catalog/catalog.json";
import evidenceFixture from "../../../../../handoff/fatima_scoring_migrations/sample_evidence_bundle.json";

import {
  cropCatalogSchema,
  evidenceDetailBundleSchema,
  type CropCatalogRecord,
  type CropReference,
  type CropScoreResult,
} from "@/lib/contracts";
import {
  buildRequirementComparisons,
  type RequirementEvidenceRow,
} from "@/lib/crops/presentation";
import { getPreparedRecommendationResult } from "@/lib/recommendations/prepared-results";
import type { ValidationGate } from "@/lib/contracts";

export type { RequirementEvidenceRow } from "@/lib/crops/presentation";

export type ProviderEvidenceSummary = {
  id: string;
  name: string;
  role: string;
  generatedAt: string;
  freshnessStatus: string;
  ageHours: number;
  sourceDataVintage: string;
  spatialResolution: string;
  sourceMode: "prepared_artifact";
};

export type PreparedCropDetail = {
  state: "ready";
  crop: CropScoreResult;
  catalog: CropCatalogRecord;
  references: CropReference[];
  comparisons: RequirementEvidenceRow[];
  providers: ProviderEvidenceSummary[];
  limitations: string[];
  validation: ValidationGate;
};

type PreparedCropDetailResult =
  | PreparedCropDetail
  | { state: "blocked"; validation: ValidationGate }
  | { state: "not_found" };

export function getPreparedCropDetail(cropId: string): PreparedCropDetailResult {
  const recommendationResult = getPreparedRecommendationResult();
  if (recommendationResult.state === "blocked") return recommendationResult;

  const crop = recommendationResult.recommendation.rankings.find(
    (ranking) => ranking.crop_id === cropId,
  );
  if (!crop) return { state: "not_found" };

  const catalog = cropCatalogSchema.parse(catalogFixture);
  const catalogCrop = catalog.crops.find((record) => record.crop_id === cropId);
  if (!catalogCrop) return { state: "not_found" };

  const evidence = evidenceDetailBundleSchema.parse(evidenceFixture);
  const references = catalog.references.filter((reference) =>
    catalogCrop.source_ids.includes(reference.source_id),
  );
  const providerEntries = Object.entries(evidence.provenance) as Array<
    [keyof typeof evidence.provenance, (typeof evidence.provenance)[keyof typeof evidence.provenance]]
  >;

  return {
    state: "ready",
    crop,
    catalog: catalogCrop,
    references,
    comparisons: buildRequirementComparisons(crop, catalogCrop),
    providers: providerEntries.map(([id, provider]) => ({
      id,
      name: provider.provider,
      role: provider.evidence_role,
      generatedAt: provider.generated_at,
      freshnessStatus: provider.freshness.status,
      ageHours: provider.freshness.age_hours,
      sourceDataVintage: provider.source_data_vintage,
      spatialResolution:
        id === "fortyguard"
          ? `${evidence.location_evidence.fortyguard_heat.granularity_m} m grid`
          : "Not reported in prepared artifact",
      sourceMode: "prepared_artifact",
    })),
    limitations: recommendationResult.recommendation.limitations,
    validation: recommendationResult.validation,
  };
}
