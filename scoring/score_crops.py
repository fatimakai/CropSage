"""Versioned, explainable deterministic crop scoring for CropSage."""

from __future__ import annotations

import argparse
import json
import math
import re
from calendar import month_abbr
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "data" / "evidence" / "plainview_evidence_bundle.json"
DEFAULT_PROFILE = ROOT / "data" / "farm-profile" / "plainview_aug_2026.sample.json"
DEFAULT_CONFIG = ROOT / "data" / "scoring" / "crop_scoring_config.json"
DEFAULT_SCHEMA = ROOT / "data" / "scoring" / "recommendation.schema.json"
DEFAULT_OUTPUT = ROOT / "data" / "scoring" / "plainview_crop_recommendations.json"
FARM_SCHEMA = ROOT / "data" / "farm-profile" / "farm_profile.schema.json"

CATEGORY_BY_FACTOR = {
    "nasa_seasonal_temperature": "thermal_heat",
    "fortyguard_temperature_fit": "thermal_heat",
    "fortyguard_threshold_exceedance": "thermal_heat",
    "fortyguard_heat_persistence": "thermal_heat",
    "open_meteo_heat_frost": "thermal_heat",
    "soil_texture": "soil",
    "soil_ph": "soil",
    "soil_drainage": "soil",
    "soil_root_zone": "soil",
    "soil_water_storage": "soil",
    "recent_rainfall": "water",
    "forecast_water_balance": "water",
    "current_soil_moisture": "water",
    "crop_water_resilience": "water",
    "irrigation_availability": "water",
    "texas_regional_suitability": "location_season",
    "planting_window": "location_season",
    "frost_free_season": "location_season",
}

MONTHS = {name.lower(): number for number, name in enumerate(month_abbr) if name}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def validate(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "$" + "".join(f"[{part!r}]" for part in error.absolute_path)
        raise ValueError(f"{label} validation failed at {path}: {error.message}")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def range_distance(value: float, range_value: dict[str, Any]) -> float | None:
    low, high = range_value.get("min"), range_value.get("max")
    if low is None or high is None:
        return None
    if value < low:
        return float(low - value)
    if value > high:
        return float(value - high)
    return 0.0


def tier_score(value: float, tiers: list[dict[str, Any]], boundary_key: str) -> float:
    for tier in tiers:
        boundary = tier[boundary_key]
        if boundary is None or value <= float(boundary):
            return float(tier["score"])
    raise ValueError("Tier configuration must end with a null boundary")


def parse_numeric_range(value: str) -> tuple[float, float] | None:
    # Soil depths and storage ranges are non-negative. Here the hyphen separates
    # bounds (for example ``100-150``); it is not a numeric minus sign.
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value or "")]
    return (numbers[0], numbers[1]) if len(numbers) >= 2 else None


def planned_year_month(profile: dict[str, Any]) -> tuple[int, int]:
    planting = profile["planting"]
    value = planting.get("planned_date") or f"{planting['planned_month']}-01"
    parsed = date.fromisoformat(value)
    return parsed.year, parsed.month


def requested_period_overlaps(start: str, end: str, profile: dict[str, Any]) -> bool:
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    planting = profile["planting"]
    if planting.get("planned_date"):
        target = date.fromisoformat(planting["planned_date"])
        return start_date <= target <= end_date
    year, month = planned_year_month(profile)
    return any(
        day.year == year and day.month == month
        for day in (start_date, end_date)
    ) or (start_date <= date(year, month, 15) <= end_date)


def evaluation_mode(profile: dict[str, Any], weather: dict[str, Any]) -> str:
    forecast_dates = {
        date.fromisoformat(row["date"][:10]) for row in weather["forecast_daily"]
    }
    planting = profile["planting"]
    if planting.get("planned_date"):
        return "planting_readiness" if date.fromisoformat(planting["planned_date"]) in forecast_dates else "planning"
    target = planned_year_month(profile)
    return "planting_readiness" if any((item.year, item.month) == target for item in forecast_dates) else "planning"


def month_span(window: str) -> set[int]:
    parts = [item.strip().lower() for item in window.split("-")]
    if len(parts) != 2 or parts[0] not in MONTHS or parts[1] not in MONTHS:
        return set()
    start, end = MONTHS[parts[0]], MONTHS[parts[1]]
    if start <= end:
        return set(range(start, end + 1))
    return set(range(start, 13)) | set(range(1, end + 1))


def circular_month_distance(month: int, months: set[int]) -> int:
    return min(min((month - other) % 12, (other - month) % 12) for other in months)


def source_confidence(
    config: dict[str, Any],
    source: str,
    crop: dict[str, Any],
    evidence_status: str | None = None,
    uses_catalog: bool = True,
) -> float:
    result = float(config["source_reliability"][source])
    if uses_catalog:
        catalog_confidence = crop["profile"].get("confidence", "low")
        result *= float(config["mapping_scores"]["catalog_confidence"].get(catalog_confidence, 0.7))
    if evidence_status:
        result *= float(config["mapping_scores"]["evidence_status_confidence"].get(evidence_status, 0.7))
    return round(max(0.0, min(1.0, result)), 4)


def factor(
    factor_id: str,
    weight: float,
    score: float | None,
    confidence: float,
    reason: str,
    sources: list[str],
    values: dict[str, Any] | None = None,
    scoring_use: str = "scored",
) -> dict[str, Any]:
    available = score is not None and weight > 0 and scoring_use == "scored"
    normalized_score = round(clamp(score), 2) if score is not None else None
    return {
        "factor_id": factor_id,
        "category": CATEGORY_BY_FACTOR[factor_id],
        "weight_percent": weight,
        "available": available,
        "score": normalized_score,
        "evidence_confidence": round(confidence if available else 0.0, 4),
        "weighted_points": round(normalized_score * weight / 100.0, 4) if available else None,
        "scoring_use": scoring_use,
        "reason": reason,
        "evidence": {"sources": sources, "values": values or {}},
    }


def temperature_score(value: float, optimal: dict[str, Any], config: dict[str, Any]) -> tuple[float | None, float | None]:
    distance = range_distance(value, optimal)
    if distance is None:
        return None, None
    return tier_score(distance, config["temperature_distance_tiers"], "max_distance_c"), distance


def ph_score(value: float, allowed: dict[str, Any]) -> tuple[float | None, float | None]:
    distance = range_distance(value, allowed)
    if distance is None:
        return None, None
    if distance == 0:
        return 100.0, distance
    if distance <= 0.5:
        return 75.0, distance
    if distance <= 1.0:
        return 45.0, distance
    return 15.0, distance


def get_heat_window(crop: dict[str, Any], name: str) -> dict[str, Any]:
    return next(row for row in crop["heat_windows"] if row["window_name"] == name)


def find_nasa_month(evidence: dict[str, Any], month: int) -> dict[str, Any] | None:
    target = month_abbr[month].lower()
    return next(
        (row for row in evidence["location_evidence"]["nasa_power_climate"]["monthly_summary"] if row["month"].lower() == target),
        None,
    )


def weighted_root_moisture(profile: list[dict[str, Any]], root_limit_cm: float) -> float | None:
    total, depth_total = 0.0, 0.0
    for row in profile:
        bounds = parse_numeric_range(row.get("depth", ""))
        if not bounds:
            continue
        low, high = bounds
        included = max(0.0, min(high, root_limit_cm) - low)
        if included:
            total += float(row["soil_moisture"]) * included
            depth_total += included
    return total / depth_total if depth_total else None


def farmer_soil_moisture(profile: dict[str, Any]) -> tuple[float | None, str | None]:
    item = profile.get("current_soil_moisture")
    if not item:
        return None, None
    measurement = item.get("measurement")
    if measurement:
        value = float(measurement["value"])
        if measurement["unit"] == "percent":
            value /= 100.0
        return value, "farmer_measurement"
    qualitative = item.get("qualitative")
    mapped = {"very_dry": 0.06, "dry": 0.1, "adequate": 0.2, "wet": 0.3, "saturated": 0.4}
    return mapped.get(qualitative), "farmer_report" if qualitative in mapped else None


def moisture_score(value: float) -> float:
    if value >= 0.25:
        return 100.0
    if value >= 0.18:
        return 80.0
    if value >= 0.12:
        return 55.0
    if value >= 0.08:
        return 30.0
    return 10.0


def irrigation_availability_score(
    irrigation: dict[str, Any] | None, crop_requirement: str
) -> float | None:
    if not irrigation or irrigation["availability"] == "unknown":
        return None
    no_irrigation_fit = {
        "often_rainfed": 90.0,
        "conditional": 60.0,
        "recommended": 35.0,
        "usually_required": 0.0,
    }.get(crop_requirement, 50.0)
    if irrigation["availability"] == "no":
        return no_irrigation_fit
    access_reliability = {
        "reliable": 100.0,
        "limited": 70.0,
        "seasonal": 65.0,
        "unreliable": 40.0,
        "unknown": 75.0,
        "not_applicable": 75.0,
    }.get(irrigation.get("reliability", "unknown"), 75.0)
    # Optional irrigation access must not make an otherwise identical farm
    # less suitable than having no irrigation at all. This matters most for
    # crops that are commonly rainfed.
    return max(access_reliability, no_irrigation_fit)


def score_one_crop(crop: dict[str, Any], evidence: dict[str, Any], profile: dict[str, Any], config: dict[str, Any], mode: str) -> dict[str, Any]:
    weights = config["weights_percent"]
    crop_profile = crop["profile"]
    _, month = planned_year_month(profile)
    factors: list[dict[str, Any]] = []
    warnings: list[str] = []
    caps: list[dict[str, Any]] = []

    nasa_month = find_nasa_month(evidence, month)
    nasa_score, nasa_distance = (None, None)
    if nasa_month:
        nasa_score, nasa_distance = temperature_score(float(nasa_month["T2M"]), crop_profile["optimal_temperature_range_c"], config)
    factors.append(factor(
        "nasa_seasonal_temperature", weights["nasa_seasonal_temperature"], nasa_score,
        source_confidence(config, "nasa_power", crop),
        "NASA monthly historical temperature is compared with the crop optimum." if nasa_score is not None else "No scoreable NASA monthly temperature or crop optimum is available.",
        ["nasa_power", "crop_catalog"],
        {"month": month_abbr[month], "temperature_c": nasa_month.get("T2M") if nasa_month else None, "distance_from_optimum_c": nasa_distance, "optimal_range_c": crop_profile["optimal_temperature_range_c"]},
    ))

    fg_windows = evidence["location_evidence"]["fortyguard_heat"]["windows"]
    active_name = config["active_heat_window"]
    active_location_window = next(row for row in fg_windows if row["window_name"] == active_name)
    fg_relevant = requested_period_overlaps(active_location_window["start_date"], active_location_window["end_date"], profile)
    heat_window = get_heat_window(crop, active_name)
    fg_confidence = source_confidence(config, "fortyguard", crop, crop_profile.get("heat_threshold_evidence_status"))
    factors.append(factor(
        "fortyguard_temperature_fit", weights["fortyguard_temperature_fit"],
        temperature_score(float(active_location_window["mean_temperature_c"]), crop_profile["optimal_temperature_range_c"], config)[0] if fg_relevant else None,
        source_confidence(config, "fortyguard", crop),
        "Farm-scale one-week mean temperature is compared with the crop optimum." if fg_relevant else "The requested planting period does not overlap the available FortyGuard heat window.",
        ["fortyguard", "crop_catalog"],
        {"window": active_name, "mean_temperature_c": active_location_window["mean_temperature_c"], "optimal_range_c": crop_profile["optimal_temperature_range_c"]},
    ))

    heat_scoreable = crop_profile["heat_threshold_scoring_use"] == "soft_penalty"
    exceedance_score = None
    persistence_score = None
    heat_use = "scored"
    if not heat_scoreable:
        heat_use = "informational_only"
        warnings.append(f"{crop['crop_name']} heat threshold is informational only and does not reduce suitability.")
    elif fg_relevant and heat_window.get("exceedance_fraction_of_window") is not None:
        exceedance_score = tier_score(float(heat_window["exceedance_fraction_of_window"]), config["heat_exceedance_fraction_tiers"], "max_fraction")
        if heat_window.get("persistence_hours") is not None:
            persistence_score = tier_score(float(heat_window["persistence_hours"]), config["persistence_hour_tiers"], "max_hours")
    factors.append(factor(
        "fortyguard_threshold_exceedance", weights["fortyguard_threshold_exceedance"], exceedance_score, fg_confidence,
        "Percentage of hours above the crop's scoreable heat threshold." if exceedance_score is not None else ("Catalog policy makes this heat threshold informational only." if not heat_scoreable else "No relevant scoreable exceedance evidence is available."),
        ["fortyguard", "crop_catalog"],
        {"window": active_name, "threshold_c": heat_window.get("heat_threshold_c"), "exceedance_hours": heat_window.get("exceedance_hours"), "exceedance_fraction": heat_window.get("exceedance_fraction_of_window")},
        heat_use,
    ))
    factors.append(factor(
        "fortyguard_heat_persistence", weights["fortyguard_heat_persistence"], persistence_score, fg_confidence,
        "Longest continuous exposure above the scoreable crop heat threshold." if persistence_score is not None else ("Catalog policy makes this heat threshold informational only." if not heat_scoreable else "No relevant scoreable persistence evidence is available."),
        ["fortyguard", "crop_catalog"],
        {"window": active_name, "persistence_hours": heat_window.get("persistence_hours")},
        heat_use,
    ))

    operational = evidence["location_evidence"]["open_meteo_weather"]["operational_summary"]
    om_parts: list[float] = []
    if mode == "planting_readiness":
        frost_days = float(operational["forecast_frost_risk_days_at_or_below_0c"])
        if frost_days == 0:
            om_parts.append(100.0)
        else:
            om_parts.append({"very_high": 0, "high": 20, "moderate": 40, "low": 70, "dormant_hardy": 90}.get(crop_profile["frost_sensitivity"], 40))
        if heat_scoreable and crop_profile["heat_stress_threshold_c"] is not None:
            exceed = max(0.0, float(operational["forecast_max_temperature_c"]) - float(crop_profile["heat_stress_threshold_c"]))
            om_parts.append(100.0 if exceed == 0 else 75.0 if exceed <= 2 else 40.0 if exceed <= 5 else 10.0)
    om_score = sum(om_parts) / len(om_parts) if om_parts else None
    factors.append(factor(
        "open_meteo_heat_frost", weights["open_meteo_heat_frost"], om_score,
        source_confidence(config, "open_meteo", crop),
        "Short-range heat and frost forecast for planting readiness." if om_score is not None else "Short-range forecast is not applicable to this future planning period.",
        ["open_meteo", "crop_catalog"],
        {"forecast_max_temperature_c": operational["forecast_max_temperature_c"], "frost_risk_days": operational["forecast_frost_risk_days_at_or_below_0c"], "heat_threshold_c": crop_profile["heat_stress_threshold_c"]},
    ))

    soil = evidence["location_evidence"]["ssurgo_soil"]
    overrides = profile.get("soil_overrides", {})
    known_texture = overrides.get("known_texture")
    if known_texture:
        texture_value = known_texture["value"].strip().lower()
        preferred = [item.lower() for item in crop_profile["preferred_soil_textures"]]
        texture_score = 100.0 if texture_value in preferred else 50.0
        texture_source = "farmer_measurement" if known_texture["source"] == "soil_test_report" else "farmer_report"
        texture_reason = "Farmer or soil-test texture overrides mapped SSURGO texture."
    else:
        texture_value = soil["surface_texture"]
        texture_label = crop["soil_fit"]["texture_fit"].lower().replace("not listed as preferred", "not listed")
        texture_score = config["mapping_scores"]["texture"].get(texture_label, 50.0)
        texture_source = "ssurgo"
        texture_reason = "Mapped SSURGO surface texture is compared with catalog preferences."
    factors.append(factor("soil_texture", weights["soil_texture"], texture_score, source_confidence(config, texture_source, crop), texture_reason, [texture_source, "crop_catalog"], {"texture": texture_value, "preferred_textures": crop_profile["preferred_soil_textures"]}))

    lab_ph = overrides.get("laboratory_ph")
    ph_value = float(lab_ph["value"]) if lab_ph else float(soil["mapped_ph_0_30cm"])
    ph_value_score, ph_distance = ph_score(ph_value, crop_profile["ph_tolerable_range"])
    ph_source = "laboratory_measurement" if lab_ph else "ssurgo"
    factors.append(factor("soil_ph", weights["soil_ph"], ph_value_score, source_confidence(config, ph_source, crop), "Laboratory pH overrides mapped SSURGO pH." if lab_ph else "Mapped SSURGO pH is compared with the catalog tolerable range.", [ph_source, "crop_catalog"], {"ph": ph_value, "distance_from_range": ph_distance, "tolerable_range": crop_profile["ph_tolerable_range"]}))

    drainage_label = crop["soil_fit"]["drainage_fit"].lower().replace(" ", "_")
    drainage_score = float(config["mapping_scores"]["drainage"].get(drainage_label, 50.0))
    factors.append(factor("soil_drainage", weights["soil_drainage"], drainage_score, source_confidence(config, "ssurgo", crop), "Mapped drainage class is compared with the crop requirement.", ["ssurgo", "crop_catalog"], {"mapped_drainage": soil["drainage_class"], "requirement": crop_profile["drainage_requirement"], "fit": crop["soil_fit"]["drainage_fit"]}))

    usable = parse_numeric_range(crop["soil_fit"]["usable_root_zone_cm"])
    required_root = crop_profile["effective_root_zone_depth_cm"].get("min")
    root_score = None
    if usable and required_root:
        ratio = usable[1] / float(required_root)
        root_score = 100.0 if ratio >= 1 else 70.0 if ratio >= 0.75 else 40.0 if ratio >= 0.5 else 10.0
    factors.append(factor("soil_root_zone", weights["soil_root_zone"], root_score, source_confidence(config, "ssurgo", crop), "Usable mapped soil depth is compared with the minimum crop root-zone requirement." if root_score is not None else "No scoreable crop root-zone requirement is available.", ["ssurgo", "crop_catalog"], {"usable_root_zone_cm": crop["soil_fit"]["usable_root_zone_cm"], "required_root_zone_cm": crop_profile["effective_root_zone_depth_cm"]}))

    storage = parse_numeric_range(crop["soil_fit"]["accessible_water_storage_mm"])
    storage_value = sum(storage) / 2 if storage else None
    storage_score = None if storage_value is None else 100.0 if storage_value >= 150 else 80.0 if storage_value >= 100 else 55.0 if storage_value >= 60 else 30.0
    factors.append(factor("soil_water_storage", weights["soil_water_storage"], storage_score, source_confidence(config, "ssurgo", crop, uses_catalog=False), "Mapped available-water storage is capacity context, not current water supply." if storage_score is not None else "No mapped water-storage range is available.", ["ssurgo"], {"accessible_storage_range_mm": crop["soil_fit"]["accessible_water_storage_mm"], "representative_storage_mm": storage_value}))

    demand_range = crop_profile["seasonal_water_demand_mm"]
    maturity = crop_profile["days_to_maturity"]
    expected_weekly = None
    if None not in (demand_range.get("min"), demand_range.get("max"), maturity.get("min"), maturity.get("max")):
        expected_weekly = ((demand_range["min"] + demand_range["max"]) / 2) / ((maturity["min"] + maturity["max"]) / 2) * 7
    recent_rain = None
    rain_source = "open_meteo"
    if profile.get("recent_rainfall"):
        rainfall = profile["recent_rainfall"]
        recent_rain = float(rainfall["amount_mm"]) * 7.0 / float(rainfall["period_days"])
        rain_source = "farmer_measurement" if rainfall.get("source") == "farm_rain_gauge" else "farmer_report"
    elif mode == "planting_readiness":
        recent_rain = float(operational["recent_7_day_rainfall_mm"])
    rain_score = None
    if recent_rain is not None and expected_weekly and expected_weekly > 0:
        ratio = recent_rain / expected_weekly
        rain_score = 100.0 if ratio >= 1 else 85.0 if ratio >= 0.75 else 65.0 if ratio >= 0.5 else 40.0 if ratio >= 0.25 else 15.0
    factors.append(factor("recent_rainfall", weights["recent_rainfall"], rain_score, source_confidence(config, rain_source, crop), "Recent rainfall is compared with an approximate weekly share of catalog seasonal water demand." if rain_score is not None else "Recent rainfall is unavailable or the requested period is outside current observations.", [rain_source, "crop_catalog"] if rain_score is not None else [], {"recent_rainfall_mm": recent_rain, "approximate_weekly_demand_mm": expected_weekly}))

    deficit = float(operational["forecast_rain_minus_et0_mm"]) if mode == "planting_readiness" else None
    balance_score = None
    if deficit is not None:
        balance_score = 100.0 if deficit >= 0 else 80.0 if deficit >= -10 else 60.0 if deficit >= -25 else 30.0 if deficit >= -50 else 10.0
    factors.append(factor("forecast_water_balance", weights["forecast_water_balance"], balance_score, source_confidence(config, "open_meteo", crop, uses_catalog=False), "Seven-day forecast rain minus reference evapotranspiration indicates atmospheric water deficit." if balance_score is not None else "Short-range water balance is not applicable to this future planning period.", ["open_meteo"] if balance_score is not None else [], {"rain_minus_et0_mm": deficit}))

    moisture_value, moisture_source = farmer_soil_moisture(profile)
    if moisture_value is None and mode == "planting_readiness":
        root_limit = float(soil["soil_root_limit_cm"])
        moisture_value = weighted_root_moisture(evidence["location_evidence"]["open_meteo_weather"]["current"]["soil_moisture_profile"], root_limit)
        moisture_source = "open_meteo" if moisture_value is not None else None
    factors.append(factor("current_soil_moisture", weights["current_soil_moisture"], moisture_score(moisture_value) if moisture_value is not None else None, source_confidence(config, moisture_source, crop, uses_catalog=False) if moisture_source else 0.0, "Farmer evidence overrides modeled soil moisture." if moisture_source and moisture_source.startswith("farmer") else ("Modeled root-profile soil moisture is used as a current screening signal." if moisture_value is not None else "Current soil moisture is unavailable for this planning period."), [moisture_source] if moisture_source else [], {"volumetric_soil_moisture_m3_m3": moisture_value}))

    demand_score = float(config["mapping_scores"]["water_demand"].get(crop_profile["water_demand_class"], 50.0))
    drought_score = float(config["mapping_scores"]["drought_tolerance"].get(crop_profile["drought_tolerance"], 50.0))
    resilience_score = (demand_score + drought_score) / 2
    factors.append(factor("crop_water_resilience", weights["crop_water_resilience"], resilience_score, source_confidence(config, "crop_catalog", crop), "Catalog water demand and drought tolerance are combined without using missing weather as a zero.", ["crop_catalog"], {"water_demand_class": crop_profile["water_demand_class"], "drought_tolerance": crop_profile["drought_tolerance"]}))

    irrigation = profile.get("irrigation")
    irrigation_score = irrigation_availability_score(
        irrigation, crop_profile["irrigation_requirement"]
    )
    factors.append(factor("irrigation_availability", weights["irrigation_availability"], irrigation_score, source_confidence(config, "farmer_report", crop), "Farmer irrigation availability is compared with the catalog requirement." if irrigation_score is not None else "Irrigation availability is unknown and is excluded from suitability.", ["farmer_report", "crop_catalog"] if irrigation_score is not None else [], {"availability": irrigation.get("availability") if irrigation else None, "reliability": irrigation.get("reliability") if irrigation else None, "crop_requirement": crop_profile["irrigation_requirement"]}))

    regional = crop_profile["regional_suitability"]
    region_score = float(config["mapping_scores"]["region"].get(regional["rating"], 0.0))
    factors.append(factor("texas_regional_suitability", weights["texas_regional_suitability"], region_score, source_confidence(config, "crop_catalog", crop), regional["basis"], ["crop_catalog"], {"region_id": regional["region_id"], "rating": regional["rating"]}))

    all_window_months = set().union(*(month_span(item) for item in crop_profile["planting_windows"])) if crop_profile["planting_windows"] else set()
    if month in all_window_months:
        planting_score, planting_distance = 100.0, 0
    elif all_window_months:
        planting_distance = circular_month_distance(month, all_window_months)
        planting_score = 40.0 if planting_distance == 1 else 0.0
    else:
        planting_score, planting_distance = 0.0, None
    factors.append(factor("planting_window", weights["planting_window"], planting_score, source_confidence(config, "crop_catalog", crop, crop_profile["planting_window_evidence_status"]), "Requested month is compared with month-level regional planting windows; exact two-week scoring is unavailable.", ["crop_catalog"], {"requested_month": month, "regional_windows": crop_profile["planting_windows"], "month_distance": planting_distance}))
    factors.append(factor("frost_free_season", weights["frost_free_season"], None, 0.0, "Inactive limitation: frost-free-season evidence has not been added.", [], {}, "inactive"))

    regionally_eligible = regional["rating"] != "not_supported"
    if not regionally_eligible:
        caps.append({"gate": "unsupported_region", "cap": config["hard_caps"]["unsupported_region"], "reason": "Catalog marks this crop unsupported in the selected Texas region."})
    if planting_score == 0:
        caps.append({"gate": "far_outside_planting_window", "cap": config["hard_caps"]["far_outside_planting_window"], "reason": "Requested month is far outside all catalog planting windows for the region."})
    if drainage_score == 0:
        caps.append({"gate": "severe_drainage_incompatibility", "cap": config["hard_caps"]["severe_drainage_incompatibility"], "reason": "Mapped drainage is incompatible with the crop requirement."})
    if irrigation and irrigation["availability"] == "no" and crop_profile["irrigation_requirement"] == "usually_required" and deficit is not None and deficit <= -25:
        caps.append({"gate": "required_irrigation_unavailable", "cap": config["hard_caps"]["required_irrigation_unavailable"], "reason": "Irrigation is unavailable for a usually-required crop during serious forecast water deficit."})

    scored = [item for item in factors if item["available"]]
    available_weight = sum(item["weight_percent"] for item in scored)
    thermal_available = any(item["available"] and item["category"] == "thermal_heat" for item in factors)
    soil_available = any(item["available"] and item["category"] == "soil" for item in factors)
    if not thermal_available or not soil_available or available_weight == 0:
        suitability = None
        status = "insufficient_evidence"
        recommendation = "insufficient_evidence"
    else:
        raw = sum(item["score"] * item["weight_percent"] for item in scored) / available_weight
        suitability = round(min([raw] + [float(item["cap"]) for item in caps]), 2)
        status = "scored"
        recommendation = next(item["label"] for item in config["recommendation_bands"] if suitability >= item["minimum"])
    active_weight = sum(weight for weight in weights.values() if weight > 0)
    confidence = round(sum(item["weight_percent"] * item["evidence_confidence"] for item in factors if item["available"]) / active_weight * 100, 2)
    confidence_band = next(item["label"] for item in config["confidence_bands"] if confidence >= item["minimum"])

    positive = sorted((item for item in scored if item["score"] >= 75), key=lambda item: item["weighted_points"], reverse=True)[:3]
    risks = sorted((item for item in scored if item["score"] < 55), key=lambda item: (item["score"], -item["weight_percent"]))[:3]
    return {
        "crop_id": crop["crop_id"],
        "crop_name": crop["crop_name"],
        "regionally_eligible": regionally_eligible,
        "status": status,
        "suitability_score": suitability,
        "recommendation": recommendation,
        "confidence_score": confidence,
        "confidence_band": confidence_band,
        "evidence_coverage_percent": round(available_weight / active_weight * 100, 2),
        "applied_caps": caps,
        "applied_gates": list(caps),
        "factors": factors,
        "key_strengths": [{"factor_id": item["factor_id"], "score": item["score"], "reason": item["reason"]} for item in positive],
        "key_risks": [{"factor_id": item["factor_id"], "score": item["score"], "reason": item["reason"]} for item in risks],
        "warnings": warnings,
    }


def score_crops(evidence: dict[str, Any], profile: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    weights = config["weights_percent"]
    if set(weights) != set(CATEGORY_BY_FACTOR):
        raise ValueError("Scoring config factor IDs do not match the engine contract")
    if not math.isclose(sum(weights.values()), 100.0, abs_tol=1e-9):
        raise ValueError("Active and inactive scoring weights must sum to 100")
    latitude = float(profile["location"]["latitude"])
    longitude = float(profile["location"]["longitude"])
    if abs(latitude - float(evidence["location"]["latitude"])) > 1e-6 or abs(longitude - float(evidence["location"]["longitude"])) > 1e-6:
        raise ValueError("Farm profile coordinates do not match this location-specific EvidenceBundle")
    mode = evaluation_mode(profile, evidence["location_evidence"]["open_meteo_weather"])
    results = [score_one_crop(crop, evidence, profile, config, mode) for crop in evidence["crop_evidence"]]

    def ranking_key(item: dict[str, Any]) -> tuple[Any, ...]:
        suitability = item["suitability_score"]
        return (
            not item["regionally_eligible"],
            suitability is None,
            -(suitability if suitability is not None else 0.0),
            -item["confidence_score"],
            item["crop_id"],
        )

    results.sort(key=ranking_key)
    eligible_rank = 0
    for overall_rank, result in enumerate(results, start=1):
        result["overall_rank"] = overall_rank
        if result["regionally_eligible"]:
            eligible_rank += 1
            result["eligible_rank"] = eligible_rank
        else:
            result["eligible_rank"] = None
    requested = profile.get("requested_crop_id")
    if requested is not None and requested not in {item["crop_id"] for item in results}:
        raise ValueError(f"Requested crop is not in the EvidenceBundle: {requested}")
    return {
        "schema_version": "1.0.0",
        "scoring_version": config["scoring_version"],
        "generated_at": evidence["generated_at"],
        "status": "validated",
        "evaluation_mode": mode,
        "profile_id": profile["profile_id"],
        "evidence_bundle_id": evidence["bundle_id"],
        "location": evidence["location"],
        "requested_crop_id": requested,
        "requested_crop_result": next((item for item in results if item["crop_id"] == requested), None),
        "rankings": results,
        "limitations": config["limitations"],
        "method": {
            "suitability": "Weighted mean of available scoreable factors, followed by explicit hard caps. Missing values are excluded, never scored as zero.",
            "confidence": "Weighted evidence reliability across all active factors; missing factors contribute no confidence.",
            "active_weight_percent": sum(value for value in weights.values() if value > 0),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    evidence, profile, config = load_json(args.evidence), load_json(args.profile), load_json(args.config)
    validate(profile, load_json(FARM_SCHEMA), "Farm profile")
    output = score_crops(evidence, profile, config)
    validate(output, load_json(args.schema), "Recommendation output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(f"Saved recommendations: {args.output}")
    print(f"Mode: {output['evaluation_mode']}")
    print(f"Crops scored: {len(output['rankings'])}")
    for item in output["rankings"][:5]:
        print(f"{item['overall_rank']:>2}. {item['crop_name']}: {item['suitability_score']} ({item['recommendation']}), confidence {item['confidence_score']}")


if __name__ == "__main__":
    main()
