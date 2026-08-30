import { describe, expect, it } from "vitest";

import catalogFixture from "../../../../../data/crop-catalog/catalog.json";
import { CROP_CATALOG_OPTIONS } from "./catalog-options";

describe("crop catalog options", () => {
  it("matches every crop ID and display name in the versioned catalog", () => {
    expect(CROP_CATALOG_OPTIONS).toEqual(
      catalogFixture.crops.map((crop) => ({ id: crop.crop_id, name: crop.common_name })),
    );
  });
});
