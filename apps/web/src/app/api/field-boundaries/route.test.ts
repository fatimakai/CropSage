import { beforeEach, describe, expect, it, vi } from "vitest";

const { createAdmin, rpc } = vi.hoisted(() => ({ createAdmin: vi.fn(), rpc: vi.fn() }));

vi.mock("@/lib/supabase/admin", () => ({
  createAdminSupabaseClient: createAdmin,
}));

import { GET } from "./route";

const feature = {
  type: "Feature" as const,
  geometry: {
    type: "MultiPolygon" as const,
    coordinates: [
      [
        [
          [-101.77, 34.17],
          [-101.75, 34.17],
          [-101.75, 34.19],
          [-101.77, 34.19],
          [-101.77, 34.17],
        ],
      ],
    ],
  },
  properties: {
    field_id: "481825000000001",
    source: "usda_csb" as const,
    area_acres: 104.2,
    representative_latitude: 34.18,
    representative_longitude: -101.76,
  },
};

describe("GET /api/field-boundaries", () => {
  beforeEach(() => {
    rpc.mockReset();
    createAdmin.mockReset();
    createAdmin.mockReturnValue({ rpc });
  });

  it("rejects a malformed or overly broad viewport before querying Supabase", async () => {
    const response = await GET(
      new Request("http://localhost/api/field-boundaries?bbox=-106,26,-94,36&zoom=10.5"),
    );

    expect(response.status).toBe(400);
    expect(rpc).not.toHaveBeenCalled();
    expect(await response.json()).toMatchObject({
      available: false,
      coverage_status: "not_loaded",
      truncated: false,
    });
  });

  it("returns validated USDA fields and fixed dataset provenance", async () => {
    rpc.mockResolvedValue({
      data: {
        available: true,
        coverage_status: "covered",
        truncated: false,
        features: [feature],
      },
      error: null,
    });

    const response = await GET(
      new Request(
        "http://localhost/api/field-boundaries?bbox=-101.78,34.16,-101.74,34.20&zoom=13",
      ),
    );

    expect(response.status).toBe(200);
    expect(rpc).toHaveBeenCalledWith("get_usda_csb_viewport", {
      p_dataset_version: "2018-2025-rev23",
      p_west: -101.78,
      p_south: 34.16,
      p_east: -101.74,
      p_north: 34.2,
      p_limit: 350,
    });
    expect(await response.json()).toEqual({
      type: "FeatureCollection",
      available: true,
      coverage_status: "covered",
      truncated: false,
      dataset_version: "2018-2025-rev23",
      features: [feature],
    });
  });

  it("fails closed when the spatial query is unavailable", async () => {
    rpc.mockResolvedValue({
      data: null,
      error: { code: "XX000", message: "database unavailable" },
    });

    const response = await GET(
      new Request(
        "http://localhost/api/field-boundaries?bbox=-101.78,34.16,-101.74,34.20&zoom=13",
      ),
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      type: "FeatureCollection",
      available: false,
      coverage_status: "not_loaded",
      truncated: false,
      dataset_version: null,
      features: [],
    });
  });

  it("fails closed when server credentials are not configured", async () => {
    createAdmin.mockImplementationOnce(() => {
      throw new Error("Supabase server environment variables are not configured.");
    });

    const response = await GET(
      new Request(
        "http://localhost/api/field-boundaries?bbox=-101.78,34.16,-101.74,34.20&zoom=13",
      ),
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ available: false, features: [] });
  });
});
