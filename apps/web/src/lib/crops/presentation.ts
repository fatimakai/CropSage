import type {
  CropCatalogRecord,
  CropScoreResult,
  ScoreFactor,
} from "@/lib/contracts";

export type RequirementEvidenceRow = {
  id: string;
  requirement: string;
  catalogValue: string;
  locationValue: string;
  status: "strong" | "mixed" | "weak" | "unknown";
  factorScore: number | null;
  note: string;
  sources: string[];
};

function factorById(crop: CropScoreResult, factorId: string) {
  return crop.factors.find((factor) => factor.factor_id === factorId);
}

function recordValue(factor: ScoreFactor | undefined, key: string) {
  return factor?.evidence.values[key];
}

function displayValue(value: unknown, suffix = ""): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "number") return `${Number(value.toFixed(2))}${suffix}`;
  if (typeof value === "string") return `${value}${suffix}`;
  if (Array.isArray(value)) return value.length ? value.join(", ") : "Unknown";
  if (typeof value === "object") {
    const range = value as { min?: unknown; max?: unknown };
    if (typeof range.min === "number" && typeof range.max === "number") {
      return `${range.min}-${range.max}${suffix}`;
    }
  }
  return "Available in evidence record";
}

function comparisonStatus(score: number | null): RequirementEvidenceRow["status"] {
  if (score === null) return "unknown";
  if (score >= 75) return "strong";
  if (score >= 45) return "mixed";
  return "weak";
}

function comparison(
  crop: CropScoreResult,
  factorId: string,
  requirement: string,
  catalogValue: string,
  locationValue: string,
  note?: string,
): RequirementEvidenceRow {
  const factor = factorById(crop, factorId);
  return {
    id: factorId,
    requirement,
    catalogValue,
    locationValue,
    status: comparisonStatus(factor?.score ?? null),
    factorScore: factor?.score ?? null,
    note: note ?? factor?.reason ?? "No comparison explanation is available.",
    sources: factor?.evidence.sources ?? [],
  };
}

export function buildRequirementComparisons(
  crop: CropScoreResult,
  catalog: CropCatalogRecord,
): RequirementEvidenceRow[] {
  const temperature = factorById(crop, "nasa_seasonal_temperature");
  const texture = factorById(crop, "soil_texture");
  const ph = factorById(crop, "soil_ph");
  const drainage = factorById(crop, "soil_drainage");
  const rootZone = factorById(crop, "soil_root_zone");
  const recentRainfall = factorById(crop, "recent_rainfall");
  const irrigation = factorById(crop, "irrigation_availability");
  const region = factorById(crop, "texas_regional_suitability");
  const planting = factorById(crop, "planting_window");
  const waterRange = catalog.water_demand.seasonal_range_mm;

  return [
    comparison(
      crop,
      "nasa_seasonal_temperature",
      "Seasonal temperature",
      `${catalog.optimal_temperature_range.min_c}-${catalog.optimal_temperature_range.max_c} C optimum`,
      `${displayValue(recordValue(temperature, "temperature_c"), " C")} (${displayValue(recordValue(temperature, "month"))})`,
    ),
    comparison(crop, "soil_texture", "Soil texture", catalog.preferred_soil_textures.join(", "), displayValue(recordValue(texture, "texture"))),
    comparison(crop, "soil_ph", "Soil pH", `${catalog.ph_tolerable_range.min}-${catalog.ph_tolerable_range.max}`, displayValue(recordValue(ph, "ph"))),
    comparison(crop, "soil_drainage", "Drainage", catalog.drainage_requirement.class.replaceAll("_", " "), displayValue(recordValue(drainage, "mapped_drainage"))),
    comparison(crop, "soil_root_zone", "Effective root zone", `${catalog.effective_root_zone_depth_cm.min}-${catalog.effective_root_zone_depth_cm.max} cm`, `${displayValue(recordValue(rootZone, "usable_root_zone_cm"))} cm mapped usable depth`),
    comparison(
      crop,
      "recent_rainfall",
      "Water demand and recent rain",
      waterRange ? `${waterRange.min}-${waterRange.max} mm seasonal demand (${catalog.water_demand.class})` : `${catalog.water_demand.class}; numeric seasonal range not established`,
      `${displayValue(recordValue(recentRainfall, "recent_rainfall_mm"), " mm")} recent rainfall`,
      "Recent rainfall is a short-term signal. It is not treated as total seasonal water supply or an irrigation prescription.",
    ),
    comparison(crop, "irrigation_availability", "Irrigation availability", catalog.irrigation_requirement.class.replaceAll("_", " "), `${displayValue(recordValue(irrigation, "availability"))}; ${displayValue(recordValue(irrigation, "reliability"))} reliability`),
    comparison(crop, "texas_regional_suitability", "Texas regional fit", displayValue(recordValue(region, "rating")), displayValue(recordValue(region, "region_id"))),
    comparison(crop, "planting_window", "Planting window", displayValue(recordValue(planting, "regional_windows")), `Requested month ${displayValue(recordValue(planting, "requested_month"))}`),
  ];
}
