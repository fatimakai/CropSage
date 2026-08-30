import "server-only";

import catalogFixture from "../../../../../data/crop-catalog/catalog.json";

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
import { getPersistedRecommendationContext } from "@/lib/recommendations/persisted-results";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";
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
  sourceMode: "persisted_artifact";
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
  location: {
    farmName: string;
    texasRegionId: string;
  };
};

type PreparedCropDetailResult =
  | PreparedCropDetail
  | { state: "blocked"; validation: ValidationGate }
  | { state: "not_found" };

function unavailableEvidenceValidation(validation: ValidationGate): ValidationGate {
  return {
    ...validation,
    outcome: "incomplete",
    render_allowed: false,
    errors: [
      ...validation.errors,
      "The validated EvidenceBundle for this assessment is unavailable.",
    ],
  };
}

export async function getPersistedCropDetail(
  assessmentSessionId: string,
  cropId: string,
): Promise<PreparedCropDetailResult> {
  const context = await getPersistedRecommendationContext(assessmentSessionId);
  const recommendationResult = context.result;
  if (recommendationResult.state === "blocked") return recommendationResult;

  const crop = recommendationResult.recommendation.rankings.find(
    (ranking) => ranking.crop_id === cropId,
  );
  if (!crop) return { state: "not_found" };

  const catalog = cropCatalogSchema.parse(catalogFixture);
  const catalogCrop = catalog.crops.find((record) => record.crop_id === cropId);
  if (!catalogCrop) return { state: "not_found" };

  if (!context.evidenceBundleId) {
    return {
      state: "blocked",
      validation: unavailableEvidenceValidation(recommendationResult.validation),
    };
  }

  const supabase = createAdminSupabaseClient();
  const { data: evidenceRecord, error: evidenceError } = await supabase
    .from("evidence_bundles")
    .select("bundle_snapshot")
    .eq("id", context.evidenceBundleId)
    .eq("status", "validated")
    .maybeSingle();
  const parsedEvidence = evidenceDetailBundleSchema.safeParse(
    evidenceRecord?.bundle_snapshot,
  );
  if (evidenceError || !parsedEvidence.success) {
    return {
      state: "blocked",
      validation: unavailableEvidenceValidation(recommendationResult.validation),
    };
  }

  const evidence = parsedEvidence.data;
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
          : "Not reported in assessment evidence",
      sourceMode: "persisted_artifact",
    })),
    limitations: recommendationResult.recommendation.limitations,
    validation: recommendationResult.validation,
    location: {
      farmName: recommendationResult.recommendation.location.farm_name,
      texasRegionId: recommendationResult.recommendation.location.texas_region_id,
    },
  };
}
