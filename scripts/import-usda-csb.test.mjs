import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_STORAGE_BUDGET_MB,
  DEFAULT_DATASET_VERSION,
  normalizeCsbFeature,
  parseArguments,
} from "./import-usda-csb.mjs";

const sourceFeature = {
  type: "Feature",
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-101.77, 34.17],
        [-101.75, 34.17],
        [-101.75, 34.19],
        [-101.77, 34.19],
        [-101.77, 34.17],
      ],
    ],
  },
  properties: {
    CSBID: 481825000000001,
    STATEFIPS: 48,
    CNTYFIPS: 189,
    CNTY: "Hale",
    CSBACRES: "104.2",
    HIST_2018: "Cotton",
  },
};

test("normalizes official fields and removes unrelated source properties", () => {
  const normalized = normalizeCsbFeature(sourceFeature);

  assert.deepEqual(normalized.properties, {
    CSBID: "481825000000001",
    STATEFIPS: "48",
    CNTYFIPS: "189",
    CNTY: "Hale",
    CSBACRES: 104.2,
  });
  assert.equal("HIST_2018" in normalized.properties, false);
});

test("rejects non-Texas and malformed geometry", () => {
  assert.throws(
    () => normalizeCsbFeature({ ...sourceFeature, properties: { ...sourceFeature.properties, STATEFIPS: 47 } }),
    /not in Texas/,
  );
  assert.throws(
    () => normalizeCsbFeature({ ...sourceFeature, geometry: { type: "Point", coordinates: [-101, 34] } }),
    /Polygon or MultiPolygon/,
  );
});

test("parses bounded batch options", () => {
  assert.deepEqual(parseArguments(["--input", "fields.geojson", "--dry-run"]), {
    input: "fields.geojson",
    datasetVersion: DEFAULT_DATASET_VERSION,
    batchSize: 250,
    dryRun: true,
    local: false,
    coverageId: "",
    coverageLabel: "",
    coverageStatus: "partial",
    coverageBbox: null,
    countyFips: null,
    countyName: null,
    maxStorageMb: DEFAULT_STORAGE_BUDGET_MB,
  });
  assert.throws(
    () => parseArguments(["--input", "fields.geojson", "--batch-size", "251"]),
    /between 1 and 250/,
  );
});

test("parses and validates coverage-pack metadata", () => {
  const options = parseArguments([
    "--input",
    "fields.geojson",
    "--coverage-id",
    "hale-pack",
    "--coverage-label",
    "Hale County pack",
    "--coverage-status",
    "ready",
    "--coverage-bbox",
    "-101.8,34.15,-101.72,34.22",
    "--county-fips",
    "189",
  ]);

  assert.deepEqual(options.coverageBbox, [-101.8, 34.15, -101.72, 34.22]);
  assert.equal(options.coverageStatus, "ready");
  assert.equal(options.countyFips, "189");
  assert.throws(
    () => parseArguments(["--input", "fields.geojson", "--coverage-id", "missing-bounds"]),
    /provided together/,
  );
});

test("rejects source records that omit required USDA provenance", () => {
  const properties = { ...sourceFeature.properties };
  delete properties.CNTYFIPS;

  assert.throws(
    () => normalizeCsbFeature({ ...sourceFeature, properties }),
    /CNTYFIPS is required/,
  );
});
