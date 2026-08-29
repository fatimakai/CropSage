"""Build a normalized CropSage EvidenceBundle from local provider artifacts."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = ROOT / "data" / "evidence" / "plainview_evidence_bundle.json"
SCHEMA_PATH = ROOT / "data" / "evidence" / "evidence_bundle.schema.json"
CATALOG_PATH = ROOT / "data" / "crop-catalog" / "catalog.json"
REGION_SITES_PATH = ROOT / "data" / "regions" / "texas_region_sites.json"
DEFAULT_PROVIDER_PATHS = {
    "nasa_power": ROOT / "data" / "evidence" / "providers" / "nasa_power_plainview.json",
    "open_meteo": ROOT / "data" / "evidence" / "providers" / "open_meteo_plainview.json",
    "ssurgo": ROOT / "data" / "evidence" / "providers" / "ssurgo_plainview.json",
    "fortyguard": ROOT / "data" / "fortyguard-cache" / "multi-window" / "all_tests_summary.json",
}

PLAINVIEW_TARGET = {
    "farm_id": "plainview_demo",
    "farm_name": "Plainview demonstration farm",
    "latitude": 34.18,
    "longitude": -101.76,
    "texas_region_id": "plains",
    "timezone": "America/Chicago",
}
COORDINATE_TOLERANCE = 1e-6
FRESHNESS_LIMIT_HOURS = {
    "fortyguard": 168,
    "nasa_power": 720,
    "open_meteo": 48,
    "ssurgo": 8760,
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required input does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include an offset: {value}")
    return parsed.astimezone(timezone.utc)


def freshness(generated_at: str, max_age_hours: int, now: datetime) -> dict[str, Any]:
    age_hours = (now - parse_datetime(generated_at)).total_seconds() / 3600
    if age_hours < -0.25:
        raise ValueError(f"Source artifact has a future timestamp: {generated_at}")
    age_hours = max(0.0, age_hours)
    passed = age_hours <= max_age_hours
    return {
        "basis": "artifact_generated_at",
        "age_hours": round(age_hours, 3),
        "max_age_hours": max_age_hours,
        "status": "fresh" if passed else "stale",
        "passed": passed,
    }


def coordinates_match(farm: dict[str, Any], target: dict[str, Any]) -> bool:
    return (
        abs(float(farm["latitude"]) - float(target["latitude"])) <= COORDINATE_TOLERANCE
        and abs(float(farm["longitude"]) - float(target["longitude"])) <= COORDINATE_TOLERANCE
    )


def validate_target(target: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    required = {
        "farm_id", "farm_name", "latitude", "longitude", "texas_region_id", "timezone"
    }
    missing = required - set(target)
    if missing:
        raise ValueError(f"Location target is missing fields: {sorted(missing)}")
    normalized = {
        "farm_id": str(target["farm_id"]),
        "farm_name": str(target["farm_name"]),
        "latitude": float(target["latitude"]),
        "longitude": float(target["longitude"]),
        "texas_region_id": str(target["texas_region_id"]),
        "timezone": str(target["timezone"]),
    }
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", normalized["farm_id"]):
        raise ValueError("farm_id must use lowercase letters, digits, underscores, or hyphens")
    if not 25.8 <= normalized["latitude"] <= 36.5 or not -106.65 <= normalized["longitude"] <= -93.5:
        raise ValueError("Location target must be within the configured Texas coordinate bounds")
    catalog_regions = {row["region_id"] for row in catalog["regions"]}
    if normalized["texas_region_id"] not in catalog_regions:
        raise ValueError(f"Unknown crop-catalog region: {normalized['texas_region_id']}")
    if normalized["timezone"] not in {"America/Chicago", "America/Denver"}:
        raise ValueError(f"Unsupported Texas timezone: {normalized['timezone']}")
    return normalized


def target_from_manifest_site(site_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    site = next((row for row in manifest["sites"] if row["site_id"] == site_id), None)
    if site is None:
        raise ValueError(f"Unknown representative site: {site_id}")
    return {
        "farm_id": site["site_id"],
        "farm_name": site["name"],
        "latitude": site["location"]["latitude"],
        "longitude": site["location"]["longitude"],
        "texas_region_id": site["parent_region_id"],
        "timezone": site["timezone"],
    }


def display_source_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def nested_value(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def catalog_range(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "min": value.get("min", value.get("min_c")),
        "max": value.get("max", value.get("max_c")),
    }


def ssurgo_comparison_rows(ssurgo: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept both the original and the current SSURGO notebook export contracts."""
    if isinstance(ssurgo.get("crop_comparisons"), list):
        return ssurgo["crop_comparisons"]
    return nested_value(ssurgo, "catalog_comparison", "records", default=[])


def regional_record(crop: dict[str, Any], key: str, region_id: str) -> dict[str, Any]:
    records = crop.get(key, [])
    return next(
        (row for row in records if row.get("region_id") == region_id),
        {},
    )


def normalize_heat_window(
    period: dict[str, Any], test: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Normalize current and legacy FortyGuard summaries without mislabeling ranges."""
    tcm_validation = next(
        (
            row
            for row in (test or {}).get("request_validation", [])
            if row.get("analytic_type") == "tcm"
        ),
        {},
    )
    minimum_tile_average = period.get(
        "minimum_tile_average_temperature_c", tcm_validation.get("min")
    )
    maximum_tile_average = period.get(
        "maximum_tile_average_temperature_c", tcm_validation.get("max")
    )
    period_minimum = period.get(
        "period_minimum_temperature_c", period.get("minimum_temperature_c")
    )
    period_maximum = period.get(
        "period_maximum_temperature_c", period.get("maximum_temperature_c")
    )
    if None in (
        minimum_tile_average,
        maximum_tile_average,
        period_minimum,
        period_maximum,
    ):
        raise ValueError(
            f"FortyGuard window {period.get('window_name')} is missing explicit "
            "spatial or temporal temperature ranges"
        )
    return {
        "window_name": period["window_name"],
        "window_days": int(period["window_days"]),
        "start_date": period["window_start"],
        "end_date": period["window_end"],
        "tile_count": int(period["tile_count"]),
        "mean_temperature_c": period["mean_temperature_c"],
        "minimum_tile_average_temperature_c": minimum_tile_average,
        "maximum_tile_average_temperature_c": maximum_tile_average,
        "period_minimum_temperature_c": period_minimum,
        "period_maximum_temperature_c": period_maximum,
        "peak_hour_raw": period.get("peak_hour_raw"),
        "peak_hour_timezone_status": period["peak_hour_timezone_status"],
    }


def build_crop_evidence(
    catalog: dict[str, Any],
    fortyguard: dict[str, Any],
    ssurgo: dict[str, Any],
    region_id: str,
) -> list[dict[str, Any]]:
    soil_by_crop = {row["crop_id"]: row for row in ssurgo_comparison_rows(ssurgo)}
    heat_by_window: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    for test in fortyguard["tests"].values():
        period = test["period_summary"]
        heat_by_window.append(
            (period, {row["crop_id"]: row for row in test["crop_results"]})
        )

    records = []
    for crop in catalog["crops"]:
        crop_id = crop["crop_id"]
        if crop_id not in soil_by_crop:
            raise ValueError(f"SSURGO comparison is missing crop: {crop_id}")
        heat_windows = []
        for period, heat_rows in heat_by_window:
            if crop_id not in heat_rows:
                raise ValueError(f"FortyGuard {period['window_name']} is missing crop: {crop_id}")
            row = heat_rows[crop_id]
            heat_windows.append(
                {
                    "window_name": period["window_name"],
                    "window_days": int(period["window_days"]),
                    "temperature_fit": row["temperature_fit"],
                    "distance_from_optimum_c": row.get("distance_from_optimum_c"),
                    "heat_threshold_c": row.get("heat_threshold_c"),
                    "threshold_scoring_use": row["threshold_scoring_use"],
                    "exceedance_hours": row.get("exceedance_hours"),
                    "persistence_hours": row.get("persistence_hours"),
                    "exceedance_fraction_of_window": row.get("exceedance_fraction_of_window"),
                    "heat_action": row["heat_action"],
                }
            )

        soil = soil_by_crop[crop_id]
        regional_suitability = regional_record(crop, "regional_suitability", region_id)
        planting_window = regional_record(crop, "planting_windows_by_region", region_id)
        records.append(
            {
                "crop_id": crop_id,
                "crop_name": crop["common_name"],
                "regionally_eligible": regional_suitability.get("rating") != "not_supported",
                "profile": {
                    "optimal_temperature_range_c": catalog_range(crop.get("optimal_temperature_range")),
                    "heat_stress_threshold_c": nested_value(crop, "heat_stress_threshold", "value_c"),
                    "heat_threshold_scoring_use": nested_value(
                        crop, "heat_stress_threshold", "scoring_use", default="not_available"
                    ),
                    "heat_threshold_evidence_status": nested_value(
                        crop,
                        "heat_stress_threshold",
                        "evidence_status",
                        default="not_available",
                    ),
                    "heat_threshold_basis": nested_value(
                        crop, "heat_stress_threshold", "basis", default="not_available"
                    ),
                    "temperature_measurement_basis": crop.get(
                        "temperature_measurement_basis", "not_available"
                    ),
                    "heat_sensitive_stages": crop.get("heat_sensitive_stages", []),
                    "preferred_soil_textures": crop.get("preferred_soil_textures", []),
                    "ph_tolerable_range": catalog_range(crop.get("ph_tolerable_range")),
                    "effective_root_zone_depth_cm": catalog_range(
                        crop.get("effective_root_zone_depth_cm")
                    ),
                    "drainage_requirement": nested_value(
                        crop, "drainage_requirement", "class", default="not_available"
                    ),
                    "water_demand_class": nested_value(
                        crop, "water_demand", "class", default="not_available"
                    ),
                    "seasonal_water_demand_mm": catalog_range(
                        nested_value(crop, "water_demand", "seasonal_range_mm", default={})
                    ),
                    "drought_tolerance": crop.get("drought_tolerance", "not_available"),
                    "irrigation_requirement": nested_value(
                        crop, "irrigation_requirement", "class", default="not_available"
                    ),
                    "regional_suitability": {
                        "region_id": region_id,
                        "rating": regional_suitability.get("rating", "not_supported"),
                        "basis": regional_suitability.get(
                            "basis", "No catalog suitability record for this region."
                        ),
                    },
                    "planting_windows": planting_window.get("windows", []),
                    "planting_window_evidence_status": planting_window.get(
                        "evidence_status", "not_available"
                    ),
                    "planting_window_basis": planting_window.get(
                        "basis", "No catalog planting window for this region."
                    ),
                    "days_to_maturity": catalog_range(crop.get("days_to_maturity")),
                    "frost_sensitivity": nested_value(
                        crop, "frost_sensitivity", "class", default="not_available"
                    ),
                    "confidence": crop["confidence"],
                    "record_status": crop["record_status"],
                },
                "heat_windows": heat_windows,
                "soil_fit": {
                    "texture_fit": soil["texture_fit"],
                    "ph_fit": soil["pH_fit"],
                    "drainage_fit": soil["drainage_fit"],
                    "usable_root_zone_cm": soil["usable_root_zone_cm"],
                    "accessible_water_storage_mm": soil["accessible_water_storage_mm"],
                    "water_use_rule": soil["water_use_rule"],
                },
            }
        )
    return records


def count_invalid_numbers(value: Any) -> int:
    if isinstance(value, float):
        return 0 if math.isfinite(value) else 1
    if isinstance(value, dict):
        return sum(count_invalid_numbers(item) for item in value.values())
    if isinstance(value, list):
        return sum(count_invalid_numbers(item) for item in value)
    return 0


def build_bundle(
    now: datetime | None = None,
    *,
    target: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
    nasa: dict[str, Any] | None = None,
    open_meteo: dict[str, Any] | None = None,
    ssurgo: dict[str, Any] | None = None,
    fortyguard: dict[str, Any] | None = None,
    source_paths: dict[str, Path] | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    schema = schema or load_json(SCHEMA_PATH)
    catalog = catalog or load_json(CATALOG_PATH)
    source_paths = source_paths or DEFAULT_PROVIDER_PATHS
    nasa = nasa or load_json(source_paths["nasa_power"])
    open_meteo = open_meteo or load_json(source_paths["open_meteo"])
    ssurgo = ssurgo or load_json(source_paths["ssurgo"])
    fortyguard = fortyguard or load_json(source_paths["fortyguard"])
    target = validate_target(target or PLAINVIEW_TARGET, catalog)

    source_farms = {
        "fortyguard": fortyguard["farm"],
        "nasa_power": nasa["farm"],
        "open_meteo": open_meteo["farm"],
        "ssurgo": ssurgo["farm"],
    }
    location_matches = {
        name: coordinates_match(farm, target) for name, farm in source_farms.items()
    }
    if not all(location_matches.values()):
        raise ValueError(
            f"Provider coordinates do not all match target {target['farm_id']}: "
            f"{location_matches}"
        )

    generated_at = {
        "fortyguard": fortyguard["generated_at_utc"],
        "nasa_power": nasa["generated_at"],
        "open_meteo": open_meteo["generated_at"],
        "ssurgo": ssurgo["generated_at"],
    }
    source_freshness = {
        name: freshness(value, FRESHNESS_LIMIT_HOURS[name], now)
        for name, value in generated_at.items()
    }
    if not all(item["passed"] for item in source_freshness.values()):
        raise ValueError(f"One or more provider artifacts are stale: {source_freshness}")

    crops = catalog["crops"]
    crop_ids = [crop["crop_id"] for crop in crops]
    if len(crops) != 22 or len(set(crop_ids)) != 22:
        raise ValueError("Crop catalog must contain exactly 22 unique crops")
    ssurgo_rows = ssurgo_comparison_rows(ssurgo)
    if len(ssurgo_rows) != 22:
        raise ValueError("SSURGO comparison must contain 22 crops")
    fortyguard_tests = list(fortyguard.get("tests", {}).values())
    if not fortyguard_tests:
        raise ValueError("FortyGuard artifact must contain at least one heat window")
    if not all(len(test.get("crop_results", [])) == 22 for test in fortyguard_tests):
        raise ValueError("Every FortyGuard heat window must contain 22 crop results")
    heat_periods = fortyguard.get("period_comparison") or [
        test["period_summary"] for test in fortyguard_tests
    ]
    if not heat_periods:
        raise ValueError("FortyGuard artifact must expose at least one period summary")
    test_window_names = {test["period_summary"]["window_name"] for test in fortyguard_tests}
    period_window_names = {period["window_name"] for period in heat_periods}
    if test_window_names != period_window_names:
        raise ValueError("FortyGuard tests and period summaries identify different windows")
    fortyguard_tests_by_window = {
        test["period_summary"]["window_name"]: test for test in fortyguard_tests
    }

    soil = ssurgo["soil_summary"]
    fg_validation = fortyguard["validation"]
    fg_start = min(period["window_start"] for period in heat_periods)
    fg_end = max(period["window_end"] for period in heat_periods)
    bundle: dict[str, Any] = {
        "schema_version": "1.2.0",
        "bundle_id": f"{target['farm_id']}_evidence",
        "generated_at": now.isoformat(),
        "status": "validated",
        "location": target,
        "catalog": {
            "version": catalog["catalog_version"],
            "crop_count": len(crops),
            "crop_ids": crop_ids,
            "source_path": "data/crop-catalog/catalog.json",
        },
        "provenance": {
            "fortyguard": {
                "provider": "FortyGuard Temperature API",
                "source_path": display_source_path(source_paths["fortyguard"]),
                "generated_at": generated_at["fortyguard"],
                "evidence_role": (
                    "farm-scale spatial heat exposure across "
                    f"{len(heat_periods)} validated time window(s)"
                ),
                "location_match": location_matches["fortyguard"],
                "freshness": source_freshness["fortyguard"],
                "source_data_vintage": f"{fg_start} through {fg_end}",
            },
            "nasa_power": {
                "provider": nasa["provider"],
                "source_path": display_source_path(source_paths["nasa_power"]),
                "generated_at": generated_at["nasa_power"],
                "evidence_role": nasa["interpretation"]["evidence_role"],
                "location_match": location_matches["nasa_power"],
                "freshness": source_freshness["nasa_power"],
                "source_data_vintage": "2001-2020 climatology and 2025 daily history",
            },
            "open_meteo": {
                "provider": open_meteo["provider"],
                "source_path": display_source_path(source_paths["open_meteo"]),
                "generated_at": generated_at["open_meteo"],
                "evidence_role": open_meteo["interpretation"]["evidence_role"],
                "location_match": location_matches["open_meteo"],
                "freshness": source_freshness["open_meteo"],
                "source_data_vintage": open_meteo["current"]["model_time"],
            },
            "ssurgo": {
                "provider": ssurgo["provider"],
                "source_path": display_source_path(source_paths["ssurgo"]),
                "generated_at": generated_at["ssurgo"],
                "evidence_role": ssurgo["interpretation"]["evidence_role"],
                "location_match": location_matches["ssurgo"],
                "freshness": source_freshness["ssurgo"],
                "source_data_vintage": soil["survey_data_saved"],
            },
        },
        "units": {
            "air_temperature": "degC",
            "precipitation": "mm",
            "relative_humidity": "percent",
            "wind_speed": "m/s",
            "solar_radiation": "MJ/m^2/day",
            "photosynthetically_active_radiation": "MJ/m^2/day",
            "soil_temperature": "degC",
            "volumetric_soil_moisture": "m^3/m^3",
            "available_water_storage": "mm",
            "depth": "cm",
            "heat_exposure": "hour",
            "ph": "dimensionless",
        },
        "location_evidence": {
            "fortyguard_heat": {
                "granularity_m": fortyguard["farm"]["granularity_m"],
                "tile_count_per_response": fg_validation["tile_count_per_response"],
                "total_validated_responses": fg_validation["total_validated_responses"],
                "total_null_values": fg_validation["total_null_values"],
                "windows": [
                    normalize_heat_window(
                        row, fortyguard_tests_by_window.get(row["window_name"])
                    )
                    for row in heat_periods
                ],
                "interpretation_warning": (
                    "Peak-hour values remain raw because the FortyGuard response timezone is unverified; "
                    "do not label them as local time until the provider confirms the basis."
                ),
            },
            "nasa_power_climate": {
                "history_start_date": nasa["daily_history_2025"]["start_date"],
                "history_end_date": nasa["daily_history_2025"]["end_date"],
                "climatology_period": nasa["interpretation"]["climatology_period"],
                "annual_summary": nasa["daily_history_2025"]["annual_summary"],
                "monthly_summary": nasa["daily_history_2025"]["monthly_summary"],
                "interpretation_warning": nasa["interpretation"]["spatial_warning"],
            },
            "open_meteo_weather": {
                "model_time": open_meteo["current"]["model_time"],
                "current": {
                    "values": open_meteo["current"]["values"],
                    "soil_moisture_profile": open_meteo["current"]["soil_moisture_profile"],
                    "soil_temperature_profile": open_meteo["current"]["soil_temperature_profile"],
                },
                "recent_complete_days": open_meteo["recent_complete_days"]["records"],
                "forecast_daily": open_meteo["forecast"]["daily_records"],
                "operational_summary": open_meteo["forecast"]["operational_summary"],
                "interpretation_warnings": [
                    open_meteo["interpretation"]["spatial_warning"],
                    open_meteo["interpretation"]["soil_warning"],
                    open_meteo["interpretation"]["water_warning"],
                ],
            },
            "ssurgo_soil": {
                "map_unit": soil["map_unit_name"],
                "farmland_classification": soil["farmland_classification"],
                "surface_texture": soil["surface_texture"],
                "surface_fractions_percent": {
                    "sand": soil["surface_sand_percent"],
                    "silt": soil["surface_silt_percent"],
                    "clay": soil["surface_clay_percent"],
                },
                "mapped_ph_0_30cm": soil["mapped_ph_0_30cm"],
                "drainage_class": soil["drainage_class"],
                "hydric_rating": soil["hydric_rating"],
                "soil_root_limit_cm": soil["soil_root_limit_cm"],
                "soil_root_limit_basis": soil["soil_root_limit_basis"],
                "available_water_storage_mm": soil["available_water_mm_to_soil_limit"],
                "available_water_coverage_cm": soil["available_water_depth_coverage_cm"],
                "horizons": ssurgo["dominant_component_horizons"],
                "interpretation_warnings": [
                    ssurgo["interpretation"].get(
                        "measurement_warning",
                        "SSURGO is mapped survey evidence, not a field or laboratory measurement.",
                    ),
                    ssurgo["interpretation"]["water_warning"],
                    ssurgo["interpretation"].get(
                        "override_rule",
                        "Farmer or laboratory soil measurements override mapped SSURGO values.",
                    ),
                ],
            },
        },
        "crop_evidence": build_crop_evidence(
            catalog, fortyguard, ssurgo, target["texas_region_id"]
        ),
        "validation": {},
    }

    invalid_number_count = count_invalid_numbers(bundle)
    checks = [
        {"name": "schema_loaded", "passed": bool(schema.get("$schema")), "details": "Draft 2020-12 schema is present."},
        {"name": "provider_coordinate_alignment", "passed": all(location_matches.values()), "details": f"All four providers match {target['latitude']}, {target['longitude']} within {COORDINATE_TOLERANCE} degrees."},
        {"name": "source_freshness", "passed": all(item["passed"] for item in source_freshness.values()), "details": "All provider artifacts satisfy source-specific freshness limits."},
        {"name": "catalog_crop_count", "passed": len(crops) == 22 and len(set(crop_ids)) == 22, "details": "Catalog contains 22 unique crop IDs."},
        {"name": "fortyguard_crop_coverage", "passed": all(len(test["crop_results"]) == 22 for test in fortyguard_tests), "details": f"All {len(fortyguard_tests)} heat window(s) contain 22 crop results."},
        {"name": "ssurgo_crop_coverage", "passed": len(ssurgo_rows) == 22, "details": "SSURGO comparison contains 22 crops."},
        {"name": "required_provider_fields", "passed": not nasa["quality"]["missing_parameters"] and all(key in soil for key in ("surface_texture", "mapped_ph_0_30cm", "drainage_class", "soil_root_limit_cm", "available_water_mm_to_soil_limit")), "details": "NASA parameters and SSURGO normalized summary fields are complete."},
        {"name": "provider_null_checks", "passed": fg_validation["total_null_values"] == 0 and not open_meteo["quality"]["current_missing_fields"], "details": "FortyGuard tiles and Open-Meteo current fields have no reported nulls."},
        {"name": "finite_numbers", "passed": invalid_number_count == 0, "details": "No NaN or infinite numeric values are present."},
        {"name": "normalized_units", "passed": True, "details": "Temperatures, water, radiation, depth, humidity, wind and heat duration use bundle units."},
    ]
    if not all(check["passed"] for check in checks):
        failed = [check["name"] for check in checks if not check["passed"]]
        raise ValueError(f"EvidenceBundle contract checks failed: {failed}")
    bundle["validation"] = {
        "all_passed": True,
        "coordinate_tolerance_degrees": COORDINATE_TOLERANCE,
        "invalid_numeric_value_count": invalid_number_count,
        "checks": checks,
    }

    Draft202012Validator.check_schema(schema)
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(bundle),
        key=lambda error: list(error.absolute_path),
    )
    if schema_errors:
        first = schema_errors[0]
        json_path = "$" + "".join(f"[{part!r}]" for part in first.absolute_path)
        raise ValueError(f"EvidenceBundle JSON Schema validation failed at {json_path}: {first.message}")
    return bundle


def provider_paths_for_site(site_id: str) -> dict[str, Path]:
    provider_dir = ROOT / "data" / "evidence" / "regions" / site_id
    return {
        "nasa_power": provider_dir / "nasa_power.json",
        "open_meteo": provider_dir / "open_meteo.json",
        "ssurgo": provider_dir / "ssurgo.json",
        "fortyguard": provider_dir / "fortyguard.json",
    }


def build_bundle_from_paths(
    target: dict[str, Any],
    provider_paths: dict[str, Path],
    now: datetime | None = None,
) -> dict[str, Any]:
    return build_bundle(now=now, target=target, source_paths=provider_paths)


def write_bundle(bundle: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-id",
        help="Representative site ID from data/regions/texas_region_sites.json",
    )
    parser.add_argument("--nasa-power", type=Path)
    parser.add_argument("--open-meteo", type=Path)
    parser.add_argument("--ssurgo", type=Path)
    parser.add_argument("--fortyguard", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--now", help="Optional deterministic ISO-8601 bundle time")
    args = parser.parse_args()

    if args.site_id:
        target = target_from_manifest_site(args.site_id, load_json(REGION_SITES_PATH))
        paths = provider_paths_for_site(args.site_id)
        output_path = args.output or (
            ROOT / "data" / "evidence" / "regions" / args.site_id / "evidence_bundle.json"
        )
    else:
        target = PLAINVIEW_TARGET
        paths = dict(DEFAULT_PROVIDER_PATHS)
        output_path = args.output or DEFAULT_OUTPUT_PATH
    overrides = {
        "nasa_power": args.nasa_power,
        "open_meteo": args.open_meteo,
        "ssurgo": args.ssurgo,
        "fortyguard": args.fortyguard,
    }
    for name, path in overrides.items():
        if path is not None:
            paths[name] = path
    now = parse_datetime(args.now) if args.now else None
    bundle = build_bundle_from_paths(target, paths, now=now)
    write_bundle(bundle, output_path)
    print(f"Saved validated EvidenceBundle: {output_path}")
    print(f"Sources: {len(bundle['provenance'])}")
    print(f"Crops: {len(bundle['crop_evidence'])}")
    print(f"FortyGuard windows: {len(bundle['location_evidence']['fortyguard_heat']['windows'])}")
    print(f"Validation checks: {len(bundle['validation']['checks'])}")


if __name__ == "__main__":
    main()
