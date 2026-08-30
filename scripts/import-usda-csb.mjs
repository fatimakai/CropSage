import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createInterface } from "node:readline";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { createClient } from "@supabase/supabase-js";

export const DEFAULT_DATASET_VERSION = "2018-2025-rev23";
export const MAX_BATCH_SIZE = 250;
export const DEFAULT_STORAGE_BUDGET_MB = 200;

function requiredText(value, label) {
  const normalized = String(value ?? "").trim();
  if (!normalized) throw new Error(`${label} is required.`);
  return normalized;
}

function normalizeFips(value, width, label) {
  const normalized = requiredText(value, label);
  if (!/^\d+$/.test(normalized) || normalized.length > width) {
    throw new Error(`${label} must contain at most ${width} digits.`);
  }
  return normalized.padStart(width, "0");
}

function coordinatesAreFinite(value) {
  if (!Array.isArray(value) || value.length === 0) return false;
  if (typeof value[0] === "number") {
    return value.length >= 2 && value.every(Number.isFinite);
  }
  return value.every(coordinatesAreFinite);
}

export function normalizeCsbFeature(feature, index = 0) {
  if (!feature || feature.type !== "Feature") {
    throw new Error(`Feature ${index + 1} is not a GeoJSON Feature.`);
  }

  const geometry = feature.geometry;
  if (
    !geometry ||
    !["Polygon", "MultiPolygon"].includes(geometry.type) ||
    !coordinatesAreFinite(geometry.coordinates)
  ) {
    throw new Error(`Feature ${index + 1} requires finite Polygon or MultiPolygon geometry.`);
  }

  const properties = feature.properties ?? {};
  const fieldId = requiredText(properties.CSBID, "CSBID");
  const stateFips = normalizeFips(properties.STATEFIPS, 2, "STATEFIPS");
  const countyFips = normalizeFips(properties.CNTYFIPS, 3, "CNTYFIPS");
  const countyName = requiredText(properties.CNTY, "CNTY");
  const areaAcres = Number(properties.CSBACRES);

  if (!/^48\d{13}$/.test(fieldId)) {
    throw new Error(`CSBID ${fieldId} is not a Texas 15-digit CSB identifier.`);
  }
  if (stateFips !== "48") throw new Error(`CSBID ${fieldId} is not in Texas.`);
  if (!Number.isFinite(areaAcres) || areaAcres <= 0) {
    throw new Error(`CSBACRES must be positive for CSBID ${fieldId}.`);
  }
  if (countyName.length > 120) throw new Error(`CNTY is too long for CSBID ${fieldId}.`);

  return {
    type: "Feature",
    geometry: {
      type: geometry.type,
      coordinates: geometry.coordinates,
    },
    properties: {
      CSBID: fieldId,
      STATEFIPS: stateFips,
      CNTYFIPS: countyFips,
      CNTY: countyName,
      CSBACRES: areaAcres,
    },
  };
}

export function parseArguments(argv) {
  const options = {
    input: "",
    datasetVersion: DEFAULT_DATASET_VERSION,
    batchSize: MAX_BATCH_SIZE,
    dryRun: false,
    local: false,
    coverageId: "",
    coverageLabel: "",
    coverageStatus: "partial",
    coverageBbox: null,
    countyFips: null,
    countyName: null,
    maxStorageMb: DEFAULT_STORAGE_BUDGET_MB,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--dry-run") {
      options.dryRun = true;
    } else if (argument === "--local") {
      options.local = true;
    } else if (argument === "--input") {
      options.input = argv[++index] ?? "";
    } else if (argument === "--dataset-version") {
      options.datasetVersion = argv[++index] ?? "";
    } else if (argument === "--batch-size") {
      options.batchSize = Number(argv[++index]);
    } else if (argument === "--coverage-id") {
      options.coverageId = argv[++index] ?? "";
    } else if (argument === "--coverage-label") {
      options.coverageLabel = argv[++index] ?? "";
    } else if (argument === "--coverage-status") {
      options.coverageStatus = argv[++index] ?? "";
    } else if (argument === "--coverage-bbox") {
      const bbox = (argv[++index] ?? "").split(",").map(Number);
      options.coverageBbox = bbox.length === 4 && bbox.every(Number.isFinite) ? bbox : null;
    } else if (argument === "--county-fips") {
      options.countyFips = argv[++index] ?? "";
    } else if (argument === "--county-name") {
      options.countyName = argv[++index] ?? "";
    } else if (argument === "--max-storage-mb") {
      options.maxStorageMb = Number(argv[++index]);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  if (!options.input) throw new Error("--input is required.");
  if (!/^\d{4}-\d{4}-rev\d+$/.test(options.datasetVersion)) {
    throw new Error("--dataset-version must look like 2018-2025-rev23.");
  }
  if (!Number.isInteger(options.batchSize) || options.batchSize < 1 || options.batchSize > 250) {
    throw new Error("--batch-size must be an integer between 1 and 250.");
  }
  if (!Number.isFinite(options.maxStorageMb) || options.maxStorageMb < 1) {
    throw new Error("--max-storage-mb must be at least 1.");
  }
  if (options.coverageId && !/^[a-z0-9]+(?:[a-z0-9-]{0,78}[a-z0-9])?$/.test(options.coverageId)) {
    throw new Error("--coverage-id must be a lowercase slug of at most 80 characters.");
  }
  if (Boolean(options.coverageId) !== Boolean(options.coverageBbox)) {
    throw new Error("--coverage-id and --coverage-bbox must be provided together.");
  }
  if (!["partial", "ready"].includes(options.coverageStatus)) {
    throw new Error("--coverage-status must be partial or ready.");
  }
  if (options.coverageBbox) {
    const [west, south, east, north] = options.coverageBbox;
    if (
      west >= east ||
      south >= north ||
      west < -106.7 ||
      east > -93.4 ||
      south < 25.8 ||
      north > 36.6
    ) {
      throw new Error("--coverage-bbox must be a west,south,east,north Texas extent.");
    }
    options.coverageLabel ||= options.coverageId;
  }
  if (options.countyFips) {
    options.countyFips = normalizeFips(options.countyFips, 3, "--county-fips");
  }

  return options;
}

export function getLocalSupabaseCredentials() {
  const cliPath = resolve("node_modules/supabase/dist/supabase.js");
  const output = execFileSync(process.execPath, [cliPath, "status", "-o", "env"], {
    cwd: resolve("."),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  const values = {};
  for (const line of output.split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (!match) continue;
    values[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
  }
  const publishableKey = values.PUBLISHABLE_KEY ?? values.ANON_KEY;
  if (!values.API_URL || !values.SECRET_KEY || !publishableKey) {
    throw new Error(
      "Local Supabase is not running or did not return API_URL, PUBLISHABLE_KEY, and SECRET_KEY.",
    );
  }
  return {
    supabaseUrl: values.API_URL,
    publishableKey,
    secretKey: values.SECRET_KEY,
  };
}

function loadEnvFile(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!match || match[1] in process.env) continue;
    let value = match[2];
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[match[1]] = value;
  }
}

async function* readFeatures(inputPath) {
  const lowerPath = inputPath.toLowerCase();
  if (lowerPath.endsWith(".geojsonl") || lowerPath.endsWith(".jsonl") || lowerPath.endsWith(".geojsonseq")) {
    const lines = createInterface({
      input: createReadStream(inputPath, { encoding: "utf8" }),
      crlfDelay: Infinity,
    });
    for await (const rawLine of lines) {
      const line = rawLine.replace(/^\x1e/, "").trim();
      if (line) yield JSON.parse(line);
    }
    return;
  }

  const size = statSync(inputPath).size;
  if (size > 100 * 1024 * 1024) {
    throw new Error("Large imports must use .geojsonl or .geojsonseq so they can be streamed.");
  }
  const document = JSON.parse(readFileSync(inputPath, "utf8").replace(/^\uFEFF/, ""));
  if (document?.type !== "FeatureCollection" || !Array.isArray(document.features)) {
    throw new Error("GeoJSON input must be a FeatureCollection.");
  }
  for (const feature of document.features) yield feature;
}

async function run() {
  const options = parseArguments(process.argv.slice(2));
  const inputPath = resolve(options.input);
  if (!existsSync(inputPath)) throw new Error(`Input file does not exist: ${inputPath}`);

  loadEnvFile(resolve("apps/web/.env.local"));
  const localCredentials = options.local ? getLocalSupabaseCredentials() : null;
  const supabaseUrl =
    localCredentials?.supabaseUrl ??
    process.env.NEXT_PUBLIC_SUPABASE_URL ??
    process.env.SUPABASE_URL;
  const secretKey =
    localCredentials?.secretKey ??
    process.env.SUPABASE_SECRET_KEY ??
    process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!options.dryRun && (!supabaseUrl || !secretKey)) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SECRET_KEY (or service-role equivalents) are required.",
    );
  }

  const client = options.dryRun
    ? null
    : createClient(supabaseUrl, secretKey, {
        auth: { autoRefreshToken: false, persistSession: false },
      });
  let batch = [];
  let processed = 0;
  let imported = 0;
  const storageBudgetBytes = options.maxStorageMb * 1024 * 1024;

  async function checkStorageBudget() {
    if (!client) return null;
    const { data, error } = await client.rpc("get_usda_csb_storage_usage", {
      p_dataset_version: options.datasetVersion,
    });
    if (error) throw new Error(`Could not inspect USDA CSB storage: ${error.message}`);
    const bytes = Number(data?.table_storage_bytes);
    if (!Number.isFinite(bytes)) throw new Error("Supabase returned invalid USDA CSB storage usage.");
    if (bytes > storageBudgetBytes) {
      throw new Error(
        `USDA CSB storage is ${(bytes / 1024 / 1024).toFixed(1)} MB, above the ${options.maxStorageMb} MB import budget.`,
      );
    }
    return bytes;
  }

  await checkStorageBudget();

  async function flush() {
    if (batch.length === 0) return;
    if (client) {
      const { data, error } = await client.rpc("import_usda_csb_fields", {
        p_dataset_version: options.datasetVersion,
        p_features: batch,
      });
      if (error) throw new Error(`Supabase rejected the batch ending at ${processed}: ${error.message}`);
      imported += Number(data);
    } else {
      imported += batch.length;
    }
    batch = [];
    if (processed % 5000 === 0) {
      await checkStorageBudget();
      process.stdout.write(`Validated ${processed} fields.\n`);
    }
  }

  for await (const feature of readFeatures(inputPath)) {
    batch.push(normalizeCsbFeature(feature, processed));
    processed += 1;
    if (batch.length === options.batchSize) await flush();
  }
  await flush();

  if (processed === 0) throw new Error("The input contains no USDA CSB features.");
  const finalStorageBytes = await checkStorageBudget();

  if (client && options.coverageId && options.coverageBbox) {
    const [west, south, east, north] = options.coverageBbox;
    const { error } = await client.rpc("register_usda_csb_coverage", {
      p_dataset_version: options.datasetVersion,
      p_coverage_id: options.coverageId,
      p_coverage_label: options.coverageLabel,
      p_coverage_status: options.coverageStatus,
      p_west: west,
      p_south: south,
      p_east: east,
      p_north: north,
      p_county_fips: options.countyFips,
      p_county_name: options.countyName,
    });
    if (error) throw new Error(`Could not register USDA CSB coverage: ${error.message}`);
  }

  process.stdout.write(
    `${options.dryRun ? "Validated" : "Imported"} ${imported} USDA CSB fields as ${options.datasetVersion}` +
      `${finalStorageBytes === null ? "" : ` (${(finalStorageBytes / 1024 / 1024).toFixed(1)} MB used)`}.\n`,
  );
}

const isDirectRun = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isDirectRun) {
  run().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
