import {
  farmProfileDraftSchema,
  farmProfileSnapshotSchema,
  type FarmProfileDraft,
  type FarmProfileSnapshot,
} from "@/lib/contracts";

type SnapshotMetadata = {
  profileId: string;
  capturedAt: string;
};

export function buildFarmProfileSnapshot(
  input: FarmProfileDraft,
  metadata: SnapshotMetadata,
): FarmProfileSnapshot {
  const profile = farmProfileDraftSchema.parse(input);

  return farmProfileSnapshotSchema.parse({
    schema_version: "1.0.0",
    profile_id: metadata.profileId,
    captured_at: metadata.capturedAt,
    ...profile,
    requested_crop_id: profile.requested_crop_id ?? null,
  });
}

export function getMissingFarmProfileFields(profile: FarmProfileDraft): string[] {
  const missing: string[] = [];

  if (!profile.farm_boundary) missing.push("farm_boundary");

  if (!profile.irrigation || profile.irrigation.availability === "unknown") {
    missing.push("irrigation");
  }
  if (!profile.soil_overrides) missing.push("soil_overrides");
  if (!profile.current_soil_moisture) missing.push("current_soil_moisture");
  if (!profile.recent_rainfall) missing.push("recent_rainfall");
  if (!profile.farmer_goal) missing.push("farmer_goal");

  return missing;
}
