import { describe, expect, it } from "vitest";

import { buildFarmProfileSnapshot, getMissingFarmProfileFields } from "@/lib/farm-profile/snapshot";

const profile = {
  location: {
    latitude: 34.18,
    longitude: -101.76,
    source: "demo_farm" as const,
    farm_name: "Plainview demonstration farm",
    location_label: "Plainview, Texas",
  },
  planting: {
    planned_month: "2026-10",
    flexibility_days: 30,
  },
  requested_crop_id: null,
  irrigation: {
    availability: "unknown" as const,
    reliability: "unknown" as const,
  },
};

describe("farm profile snapshots", () => {
  it("adds stable server metadata without changing the validated farmer input", () => {
    const snapshot = buildFarmProfileSnapshot(profile, {
      profileId: "profile_1234567890abcdef",
      capturedAt: "2026-08-29T12:00:00.000Z",
    });

    expect(snapshot.schema_version).toBe("1.0.0");
    expect(snapshot.profile_id).toBe("profile_1234567890abcdef");
    expect(snapshot.location.latitude).toBe(34.18);
    expect(snapshot.planting.planned_month).toBe("2026-10");
  });

  it("keeps unknown and omitted optional evidence explicit", () => {
    expect(getMissingFarmProfileFields(profile)).toEqual([
      "farm_boundary",
      "irrigation",
      "soil_overrides",
      "current_soil_moisture",
      "recent_rainfall",
      "farmer_goal",
    ]);
  });
});
