import { NextResponse } from "next/server";

import {
  fieldBoundaryViewportDataSchema,
  fieldBoundaryViewportQuerySchema,
  USDA_CSB_DATASET_VERSION,
  type FieldBoundaryCollectionResponse,
} from "@/lib/contracts";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";

export const dynamic = "force-dynamic";

const emptyResponse: FieldBoundaryCollectionResponse = {
  type: "FeatureCollection",
  features: [],
  available: false,
  coverage_status: "not_loaded",
  truncated: false,
  dataset_version: null,
};

function noStoreResponse(status: number) {
  return NextResponse.json(emptyResponse, {
    status,
    headers: { "cache-control": "no-store" },
  });
}

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const bbox = searchParams.get("bbox")?.split(",").map(Number);
  const zoom = Number(searchParams.get("zoom"));
  const parsed = fieldBoundaryViewportQuerySchema.safeParse({ bbox, zoom });

  if (!parsed.success) return noStoreResponse(400);

  const [west, south, east, north] = parsed.data.bbox;
  let data: unknown;
  let error: { code?: string; message: string } | null;

  try {
    const admin = createAdminSupabaseClient();
    const result = await admin.rpc("get_usda_csb_viewport", {
      p_dataset_version: USDA_CSB_DATASET_VERSION,
      p_west: west,
      p_south: south,
      p_east: east,
      p_north: north,
      p_limit: 350,
    });
    data = result.data;
    error = result.error;
  } catch (caught) {
    console.error("USDA CSB viewport query could not start", {
      message: caught instanceof Error ? caught.message : "Unknown configuration error",
    });
    return noStoreResponse(503);
  }

  if (error) {
    console.error("USDA CSB viewport query failed", {
      code: error.code,
      message: error.message,
    });
    return noStoreResponse(503);
  }

  const viewport = fieldBoundaryViewportDataSchema.safeParse(data);
  if (!viewport.success) {
    console.error("USDA CSB viewport query returned an invalid shape", {
      issue: viewport.error.issues[0]?.message,
    });
    return noStoreResponse(503);
  }

  const response: FieldBoundaryCollectionResponse = {
    type: "FeatureCollection",
    features: viewport.data.features,
    available: viewport.data.available,
    coverage_status: viewport.data.coverage_status,
    truncated: viewport.data.truncated,
    dataset_version: viewport.data.available ? USDA_CSB_DATASET_VERSION : null,
  };

  return NextResponse.json(response, {
    headers: {
      "cache-control": "public, max-age=300, stale-while-revalidate=3600",
    },
  });
}
