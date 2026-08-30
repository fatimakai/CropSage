import area from "@turf/area";
import pointOnFeature from "@turf/point-on-feature";

import { farmBoundarySchema, type FarmBoundary } from "@/lib/contracts";

const SQUARE_METERS_PER_ACRE = 4_046.8564224;

export type FarmBoundarySummary = {
  geometry: FarmBoundary;
  areaAcres: number;
  representativePoint: {
    latitude: number;
    longitude: number;
  };
};

export function summarizeFarmBoundary(geometry: unknown): FarmBoundarySummary | null {
  const parsed = farmBoundarySchema.safeParse(geometry);
  if (!parsed.success) return null;

  const feature = {
    type: "Feature" as const,
    properties: {},
    geometry: parsed.data,
  };
  const areaAcres = area(feature) / SQUARE_METERS_PER_ACRE;
  if (!Number.isFinite(areaAcres) || areaAcres <= 0) return null;

  const representative = pointOnFeature(feature).geometry.coordinates;
  return {
    geometry: parsed.data,
    areaAcres,
    representativePoint: {
      latitude: representative[1],
      longitude: representative[0],
    },
  };
}
