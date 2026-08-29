import { z } from "zod";

const numericRangeSchema = z.object({
  min: z.number(),
  max: z.number(),
});

export const cropCatalogRecordSchema = z.object({
  crop_id: z.string().min(1),
  common_name: z.string().min(1),
  scientific_name: z.string().min(1),
  production_use: z.string().min(1),
  variety_scope: z.string().min(1),
  supported_texas_regions: z.array(z.string()),
  regional_suitability: z.array(
    z.object({
      region_id: z.string(),
      rating: z.string(),
      basis: z.string(),
    }),
  ),
  planting_windows_by_region: z.array(
    z.object({
      region_id: z.string(),
      windows: z.array(z.string()),
      basis: z.string(),
      evidence_status: z.string(),
      source_ids: z.array(z.string()),
    }),
  ),
  days_to_maturity: numericRangeSchema.extend({
    basis: z.string(),
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  optimal_temperature_range: z.object({
    min_c: z.number(),
    max_c: z.number(),
    basis: z.string(),
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  heat_stress_threshold: z.object({
    value_c: z.number().nullable(),
    scoring_use: z.string(),
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  heat_sensitive_stages: z.array(z.string()),
  frost_sensitivity: z.object({
    class: z.string(),
    description: z.string(),
    source_ids: z.array(z.string()),
  }),
  preferred_soil_textures: z.array(z.string()),
  ph_tolerable_range: numericRangeSchema.extend({
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  effective_root_zone_depth_cm: numericRangeSchema.extend({
    basis: z.string(),
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  drainage_requirement: z.object({
    class: z.string(),
    description: z.string(),
    source_ids: z.array(z.string()),
  }),
  water_demand: z.object({
    class: z.string(),
    seasonal_range_mm: numericRangeSchema.nullable(),
    basis: z.string(),
    evidence_status: z.string(),
    source_ids: z.array(z.string()),
  }),
  drought_tolerance: z.string(),
  irrigation_requirement: z.object({
    class: z.string(),
    description: z.string(),
    source_ids: z.array(z.string()),
  }),
  source_ids: z.array(z.string()),
  confidence: z.string(),
  last_reviewed: z.iso.date(),
  assumptions: z.array(z.string()),
  catalog_version: z.string(),
  record_status: z.string(),
});

export const cropCatalogSchema = z.object({
  catalog_version: z.string(),
  references: z.array(
    z.object({
      source_id: z.string(),
      title: z.string(),
      publisher: z.string(),
      source_type: z.string(),
      url: z.url(),
      supports: z.array(z.string()),
      accessed_on: z.iso.date(),
    }),
  ),
  crops: z.array(cropCatalogRecordSchema).length(22),
});

export const providerProvenanceSchema = z.object({
  provider: z.string(),
  generated_at: z.iso.datetime({ offset: true }),
  evidence_role: z.string(),
  location_match: z.boolean(),
  freshness: z.object({
    age_hours: z.number().min(0),
    max_age_hours: z.number().positive(),
    status: z.string(),
    passed: z.boolean(),
  }),
  source_data_vintage: z.string(),
});

export const evidenceDetailBundleSchema = z.object({
  bundle_id: z.string(),
  generated_at: z.iso.datetime({ offset: true }),
  provenance: z.object({
    fortyguard: providerProvenanceSchema,
    nasa_power: providerProvenanceSchema,
    open_meteo: providerProvenanceSchema,
    ssurgo: providerProvenanceSchema,
  }),
  location_evidence: z.object({
    fortyguard_heat: z.object({ granularity_m: z.number().positive() }),
  }),
});

export type CropCatalogRecord = z.infer<typeof cropCatalogRecordSchema>;
export type CropReference = z.infer<typeof cropCatalogSchema>["references"][number];
export type ProviderProvenance = z.infer<typeof providerProvenanceSchema>;
