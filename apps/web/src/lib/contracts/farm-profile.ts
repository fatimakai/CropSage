import { z } from "zod";

const cropIdSchema = z.string().regex(/^[a-z0-9][a-z0-9_]*$/);

export const farmLocationSchema = z
  .object({
    latitude: z.number().min(25.8).max(36.6),
    longitude: z.number().min(-106.7).max(-93.4),
    source: z.enum([
      "map_pin",
      "gps",
      "address_geocoding",
      "demo_farm",
      "manual_coordinates",
    ]),
    farm_name: z.string().trim().min(1).max(120).optional(),
    location_label: z.string().trim().min(1).max(200).optional(),
  })
  .strict();

export const plantingPlanSchema = z
  .object({
    planned_date: z.iso.date().optional(),
    planned_month: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/).optional(),
    flexibility_days: z.number().int().min(0).max(120).optional(),
  })
  .strict()
  .refine(
    (value) =>
      Number(Boolean(value.planned_date)) + Number(Boolean(value.planned_month)) === 1,
    "Choose an exact planting date or a planting month.",
  );

export const waterCapacitySchema = z
  .object({
    value: z.number().min(0),
    unit: z.enum([
      "gpm",
      "cfs",
      "liters_per_second",
      "cubic_meters_per_hour",
      "gallons_per_day",
      "acre_feet_per_year",
    ]),
    source: z.enum(["farmer", "irrigation_district", "system_documentation", "unknown"]),
  })
  .strict();

export const irrigationInputSchema = z
  .object({
    availability: z.enum(["yes", "no", "unknown"]),
    reliability: z
      .enum(["reliable", "limited", "seasonal", "unreliable", "unknown", "not_applicable"])
      .optional(),
    method: z
      .enum(["drip", "center_pivot", "sprinkler", "furrow", "flood", "subsurface", "other", "unknown"])
      .optional(),
    water_source: z
      .enum(["well", "canal", "pond", "municipal", "captured_rainwater", "multiple", "other", "unknown"])
      .optional(),
    well_pumping_capacity_gpm: z.number().min(0).optional(),
    canal_allocation_or_capacity: waterCapacitySchema.optional(),
    notes: z.string().trim().min(1).max(1000).optional(),
  })
  .strict();

export const soilOverridesSchema = z
  .object({
    known_texture: z
      .object({
        value: z.string().trim().min(1).max(100),
        source: z.enum(["farmer", "soil_test_report"]),
        observed_or_tested_at: z.iso.date().optional(),
      })
      .strict()
      .optional(),
    laboratory_ph: z
      .object({
        value: z.number().min(0).max(14),
        tested_at: z.iso.date(),
        laboratory_name: z.string().trim().min(1).max(200).optional(),
        report_reference: z.string().trim().min(1).max(300).optional(),
      })
      .strict()
      .optional(),
  })
  .strict()
  .refine((value) => Boolean(value.known_texture || value.laboratory_ph), {
    message: "Add at least one soil override.",
  });

export const currentSoilMoistureSchema = z
  .object({
    qualitative: z.enum(["very_dry", "dry", "adequate", "wet", "saturated", "unknown"]).optional(),
    measurement: z
      .object({
        value: z.number().min(0),
        unit: z.enum(["m3_per_m3", "percent"]),
        depth_cm: z.number().min(0).optional(),
        measured_at: z.iso.datetime().optional(),
      })
      .strict()
      .optional(),
    source: z.enum(["farmer_observation", "sensor", "other", "unknown"]),
    notes: z.string().trim().min(1).max(1000).optional(),
  })
  .strict()
  .refine((value) => Boolean(value.qualitative || value.measurement), {
    message: "Add an observed or measured soil moisture value.",
  });

export const recentRainfallSchema = z
  .object({
    amount_mm: z.number().min(0),
    period_days: z.number().int().min(1).max(90),
    period_end_date: z.iso.date().optional(),
    source: z.enum(["farmer", "farm_rain_gauge"]),
  })
  .strict();

export const farmerGoalSchema = z
  .object({
    primary_goal: z
      .enum([
        "maximize_yield",
        "reduce_water_use",
        "heat_resilience",
        "lower_input_cost",
        "market_crop",
        "household_use",
        "soil_health",
        "other",
      ])
      .optional(),
    preferred_crop_ids: z.array(cropIdSchema).max(22).optional(),
    excluded_crop_ids: z.array(cropIdSchema).max(22).optional(),
    notes: z.string().trim().min(1).max(1500).optional(),
  })
  .strict()
  .refine(
    (value) =>
      Boolean(
        value.primary_goal ||
          value.notes ||
          value.preferred_crop_ids?.length ||
          value.excluded_crop_ids?.length,
      ),
    { message: "Add at least one farm goal." },
  );

export const farmProfileDraftSchema = z
  .object({
    location: farmLocationSchema,
    planting: plantingPlanSchema,
    requested_crop_id: cropIdSchema.nullable().optional(),
    irrigation: irrigationInputSchema.optional(),
    soil_overrides: soilOverridesSchema.optional(),
    current_soil_moisture: currentSoilMoistureSchema.optional(),
    recent_rainfall: recentRainfallSchema.optional(),
    farmer_goal: farmerGoalSchema.optional(),
  })
  .strict();

export const farmProfileSnapshotSchema = farmProfileDraftSchema.extend({
  schema_version: z.literal("1.0.0"),
  profile_id: z.string().regex(/^[a-z0-9][a-z0-9_-]{2,79}$/),
  captured_at: z.iso.datetime(),
});

export type FarmLocation = z.infer<typeof farmLocationSchema>;
export type PlantingPlan = z.infer<typeof plantingPlanSchema>;
export type IrrigationInput = z.infer<typeof irrigationInputSchema>;
export type FarmProfileDraft = z.infer<typeof farmProfileDraftSchema>;
export type FarmProfileSnapshot = z.infer<typeof farmProfileSnapshotSchema>;
