import { z } from "zod";

import { farmBoundarySchema } from "./farm-profile";

export const USDA_CSB_DATASET_VERSION = "2018-2025-rev23";
export const fieldBoundaryCoverageStatusSchema = z.enum([
  "covered",
  "partial",
  "not_loaded",
]);

export const fieldBoundaryViewportQuerySchema = z
  .object({
    bbox: z.tuple([
      z.number().min(-106.7).max(-93.4),
      z.number().min(25.8).max(36.6),
      z.number().min(-106.7).max(-93.4),
      z.number().min(25.8).max(36.6),
    ]),
    zoom: z.number().min(10.5).max(19),
  })
  .strict()
  .superRefine(({ bbox }, context) => {
    const [west, south, east, north] = bbox;
    if (west >= east || south >= north) {
      context.addIssue({
        code: "custom",
        message: "The field-boundary viewport must use west,south,east,north order.",
      });
    }
    if (east - west > 1.5 || north - south > 1.5) {
      context.addIssue({
        code: "custom",
        message: "Zoom in before requesting mapped field boundaries.",
      });
    }
  });

export const fieldBoundaryPropertiesSchema = z
  .object({
    field_id: z.string().trim().min(1).max(160),
    source: z.literal("usda_csb"),
    area_acres: z.number().positive().optional(),
    representative_latitude: z.number().min(-90).max(90).optional(),
    representative_longitude: z.number().min(-180).max(180).optional(),
  })
  .strict();

export const fieldBoundaryFeatureSchema = z
  .object({
    type: z.literal("Feature"),
    geometry: farmBoundarySchema,
    properties: fieldBoundaryPropertiesSchema,
  })
  .strict();

export const fieldBoundaryCollectionResponseSchema = z
  .object({
    type: z.literal("FeatureCollection"),
    features: z.array(fieldBoundaryFeatureSchema),
    available: z.boolean(),
    coverage_status: fieldBoundaryCoverageStatusSchema,
    truncated: z.boolean(),
    dataset_version: z.string().trim().min(1).max(120).nullable(),
  })
  .strict();

export const fieldBoundaryViewportDataSchema = z
  .object({
    available: z.boolean(),
    coverage_status: fieldBoundaryCoverageStatusSchema,
    truncated: z.boolean(),
    features: z.array(fieldBoundaryFeatureSchema).max(500),
  })
  .strict();

export type FieldBoundaryFeature = z.infer<typeof fieldBoundaryFeatureSchema>;
export type FieldBoundaryCollectionResponse = z.infer<
  typeof fieldBoundaryCollectionResponseSchema
>;
export type FieldBoundaryViewportQuery = z.infer<typeof fieldBoundaryViewportQuerySchema>;
