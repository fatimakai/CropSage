"""Single recommendation entry point for CropSage interfaces and agents.

This module deliberately contains no HTTP or LLM code. A future API route and the
CropSage agent should both call :func:`recommend_crops`, keeping scoring behavior
identical in every interface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scoring.score_crops import load_json, score_crops, validate
from scoring.validate_recommendations import validate_ranking_contract


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "regions" / "texas_region_sites.json"
EVIDENCE_ROOT = ROOT / "data" / "evidence" / "regions"
EVIDENCE_SCHEMA_PATH = ROOT / "data" / "evidence" / "evidence_bundle.schema.json"
FARM_PROFILE_SCHEMA_PATH = ROOT / "data" / "farm-profile" / "farm_profile.schema.json"
CONFIG_PATH = ROOT / "data" / "scoring" / "crop_scoring_config.json"
RECOMMENDATION_SCHEMA_PATH = ROOT / "data" / "scoring" / "recommendation.schema.json"

SERVICE_VERSION = "1.0.0"
REQUIRED_SCORING_VERSION = "1.0.1"
PLANTING_MONTH_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")

# Coarse rejection envelope only. The service reports that this is not a GIS
# boundary test; exact Texas polygon resolution belongs in the production API.
TEXAS_ENVELOPE = {
    "minimum_latitude": 25.8,
    "maximum_latitude": 36.6,
    "minimum_longitude": -106.7,
    "maximum_longitude": -93.4,
}

IRRIGATION_AVAILABILITY = {"yes", "no", "unknown"}
IRRIGATION_RELIABILITY = {
    "reliable",
    "limited",
    "seasonal",
    "unreliable",
    "unknown",
    "not_applicable",
}
IRRIGATION_METHODS = {
    "drip",
    "center_pivot",
    "sprinkler",
    "furrow",
    "flood",
    "subsurface",
    "other",
    "unknown",
}
SOIL_TEST_FIELDS = {
    "ph",
    "tested_at",
    "laboratory_name",
    "report_reference",
    "texture",
    "texture_source",
    "texture_observed_or_tested_at",
}


class RecommendationServiceError(ValueError):
    """An actionable validation or cached-evidence error."""


def _read_public_json(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "CropSage/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed public API URLs
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecommendationServiceError("The address lookup service is temporarily unavailable") from exc


def resolve_texas_location(location_query: str) -> dict[str, Any]:
    """Resolve a Texas street address, ZIP code, town, or place name to coordinates."""
    if not isinstance(location_query, str) or len(location_query.strip()) < 2:
        raise RecommendationServiceError("Please enter a Texas address, ZIP code, or nearby town")
    query = re.sub(r"^(near|in|outside|around)\s+", "", location_query.strip(), flags=re.I)

    census_url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urlencode(
        {"address": query, "benchmark": "Public_AR_Current", "format": "json"}
    )
    try:
        census = _read_public_json(census_url)
        matches = census.get("result", {}).get("addressMatches", [])
        if matches:
            match = matches[0]
            coordinates = match.get("coordinates", {})
            latitude, longitude = _validate_farmer_location(coordinates.get("y"), coordinates.get("x"))
            return {
                "latitude": latitude,
                "longitude": longitude,
                "display_name": match.get("matchedAddress") or query,
                "provider": "us_census_geocoder",
                "original_query": location_query,
            }
    except RecommendationServiceError:
        # A no-match or temporary Census failure still permits the place-name fallback.
        pass

    place_query = query if re.search(r"\b(texas|tx)\b", query, re.I) else f"{query}, Texas"
    meteo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
        {
            "name": place_query,
            "count": 10,
            "language": "en",
            "format": "json",
            "countryCode": "US",
        }
    )
    meteo = _read_public_json(meteo_url)
    candidates = [
        item
        for item in meteo.get("results", [])
        if str(item.get("admin1", "")).casefold() == "texas"
    ]
    if not candidates:
        raise RecommendationServiceError(
            "I could not find that Texas location. Try a full address, ZIP code, or nearby town and state."
        )
    match = candidates[0]
    latitude, longitude = _validate_farmer_location(match.get("latitude"), match.get("longitude"))
    parts = [match.get("name"), match.get("admin2"), match.get("admin1")]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "display_name": ", ".join(str(part) for part in parts if part),
        "provider": "open_meteo_geocoding",
        "original_query": location_query,
    }


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise RecommendationServiceError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RecommendationServiceError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise RecommendationServiceError(f"{label} must be finite")
    return number


def _validate_farmer_location(latitude: Any, longitude: Any) -> tuple[float, float]:
    lat = _finite_number(latitude, "latitude")
    lon = _finite_number(longitude, "longitude")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise RecommendationServiceError("Farmer coordinates are outside valid latitude/longitude ranges")
    if not (
        TEXAS_ENVELOPE["minimum_latitude"] <= lat <= TEXAS_ENVELOPE["maximum_latitude"]
        and TEXAS_ENVELOPE["minimum_longitude"] <= lon <= TEXAS_ENVELOPE["maximum_longitude"]
    ):
        raise RecommendationServiceError(
            "Location is outside CropSage's current coarse Texas service envelope"
        )
    return lat, lon


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _proxy_quality(distance_km: float) -> str:
    if distance_km <= 1:
        return "exact_or_adjacent"
    if distance_km <= 50:
        return "nearby_proxy"
    if distance_km <= 150:
        return "regional_proxy"
    return "distant_proxy"


def _resolve_cached_site(latitude: float, longitude: float) -> tuple[dict[str, Any], Path, float]:
    manifest = load_json(MANIFEST_PATH)
    available: list[tuple[float, dict[str, Any], Path]] = []
    for site in manifest.get("sites", []):
        evidence_path = EVIDENCE_ROOT / site["site_id"] / "evidence_bundle.json"
        if not evidence_path.is_file():
            continue
        site_location = site["location"]
        distance = _haversine_km(
            latitude,
            longitude,
            float(site_location["latitude"]),
            float(site_location["longitude"]),
        )
        available.append((distance, site, evidence_path))
    if not available:
        raise RecommendationServiceError("No validated regional EvidenceBundles are cached")
    distance, site, evidence_path = min(available, key=lambda item: (item[0], item[1]["site_id"]))
    return site, evidence_path, distance


def _validate_iso_date(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise RecommendationServiceError(f"{label} must be an ISO date in YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RecommendationServiceError(f"{label} must be an ISO date in YYYY-MM-DD format") from exc
    return parsed.isoformat()


def _soil_overrides(soil_test_values: dict[str, Any] | None) -> dict[str, Any] | None:
    if soil_test_values is None:
        return None
    if not isinstance(soil_test_values, dict):
        raise RecommendationServiceError("soil_test_values must be an object")
    unknown = sorted(set(soil_test_values) - SOIL_TEST_FIELDS)
    if unknown:
        raise RecommendationServiceError(f"Unsupported soil-test fields: {', '.join(unknown)}")

    overrides: dict[str, Any] = {}
    if "ph" in soil_test_values:
        ph = _finite_number(soil_test_values["ph"], "soil-test pH")
        if not 0 <= ph <= 14:
            raise RecommendationServiceError("soil-test pH must be between 0 and 14")
        if "tested_at" not in soil_test_values:
            raise RecommendationServiceError("soil-test tested_at is required when pH is supplied")
        laboratory_ph: dict[str, Any] = {
            "value": ph,
            "tested_at": _validate_iso_date(soil_test_values["tested_at"], "soil-test tested_at"),
        }
        for source_key, target_key in (
            ("laboratory_name", "laboratory_name"),
            ("report_reference", "report_reference"),
        ):
            if source_key in soil_test_values:
                laboratory_ph[target_key] = soil_test_values[source_key]
        overrides["laboratory_ph"] = laboratory_ph

    if "texture" in soil_test_values:
        texture = soil_test_values["texture"]
        if not isinstance(texture, str) or not texture.strip():
            raise RecommendationServiceError("soil-test texture must be a non-empty string")
        source = soil_test_values.get("texture_source", "soil_test_report")
        if source not in {"farmer", "soil_test_report"}:
            raise RecommendationServiceError("texture_source must be farmer or soil_test_report")
        known_texture: dict[str, Any] = {"value": texture.strip().lower(), "source": source}
        if "texture_observed_or_tested_at" in soil_test_values:
            known_texture["observed_or_tested_at"] = _validate_iso_date(
                soil_test_values["texture_observed_or_tested_at"],
                "texture_observed_or_tested_at",
            )
        overrides["known_texture"] = known_texture

    if not overrides:
        raise RecommendationServiceError("soil_test_values must contain ph and/or texture")
    return overrides


def _irrigation_profile(
    availability: str,
    reliability: str | None,
    method: str | None,
) -> dict[str, Any]:
    if availability not in IRRIGATION_AVAILABILITY:
        raise RecommendationServiceError("irrigation_availability must be yes, no, or unknown")
    reliability = reliability or "unknown"
    method = method or "unknown"
    if reliability not in IRRIGATION_RELIABILITY:
        raise RecommendationServiceError(f"Unsupported irrigation reliability: {reliability}")
    if method not in IRRIGATION_METHODS:
        raise RecommendationServiceError(f"Unsupported irrigation method: {method}")
    if availability == "no":
        reliability, method = "not_applicable", "unknown"
    elif availability == "unknown":
        reliability, method = "unknown", "unknown"
    elif reliability == "not_applicable":
        raise RecommendationServiceError("Available irrigation cannot have not_applicable reliability")
    return {
        "availability": availability,
        "reliability": reliability,
        "method": method,
        "water_source": "unknown",
    }


def _profile_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"service_request_{digest}"


def prepare_recommendation_inputs(farm_profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve an intake FarmProfile to the exact cached inputs used by scoring."""
    validate(farm_profile, load_json(FARM_PROFILE_SCHEMA_PATH), "Farm profile")
    farmer_location = farm_profile["location"]
    farmer_latitude, farmer_longitude = _validate_farmer_location(
        farmer_location["latitude"], farmer_location["longitude"]
    )

    site, evidence_path, distance_km = _resolve_cached_site(farmer_latitude, farmer_longitude)
    evidence = load_json(evidence_path)
    validate(evidence, load_json(EVIDENCE_SCHEMA_PATH), "Cached EvidenceBundle")
    config = load_json(CONFIG_PATH)
    if config.get("scoring_version") != REQUIRED_SCORING_VERSION:
        raise RecommendationServiceError(
            f"Recommendation service requires scoring engine {REQUIRED_SCORING_VERSION}; "
            f"found {config.get('scoring_version')}"
        )

    requested_crop_id = farm_profile.get("requested_crop_id")
    if requested_crop_id is not None and requested_crop_id not in set(evidence["catalog"]["crop_ids"]):
        raise RecommendationServiceError(f"Unknown crop_id {requested_crop_id!r}")

    resolved_profile = deepcopy(farm_profile)
    resolution_identity = {
        "source_profile_id": farm_profile["profile_id"],
        "site_id": site["site_id"],
        "evidence_bundle_id": evidence["bundle_id"],
    }
    resolved_profile["profile_id"] = _profile_id(resolution_identity)
    resolved_profile.pop("farm_boundary", None)
    evidence_location = evidence["location"]
    resolved_profile["location"] = {
        "latitude": float(evidence_location["latitude"]),
        "longitude": float(evidence_location["longitude"]),
        "farm_name": evidence_location["farm_name"],
        "location_label": site["nearby_agricultural_center"],
        "source": "demo_farm",
    }
    validate(resolved_profile, load_json(FARM_PROFILE_SCHEMA_PATH), "Resolved scoring profile")

    rounded_distance = round(distance_km, 2)
    quality = _proxy_quality(distance_km)
    limitations = [
        "Texas membership currently uses a coarse coordinate envelope, not an official state-boundary polygon.",
        "Provider evidence comes from the nearest cached representative site, not the farmer's exact parcel.",
        "Use live location-specific provider collection before treating the result as field-specific advice.",
    ]
    if quality == "distant_proxy":
        limitations.append(
            "The nearest cached site is more than 150 km away; treat this result as exploratory only."
        )

    return {
        "farm_profile": resolved_profile,
        "evidence_bundle": evidence,
        "scoring_config": config,
        "location_resolution": {
            "method": "nearest_cached_representative_site",
            "source_profile_id": farm_profile["profile_id"],
            "source_coordinates": {
                "latitude": farmer_latitude,
                "longitude": farmer_longitude,
            },
            "site_id": site["site_id"],
            "site_name": site["name"],
            "parent_catalog_region_id": site["parent_region_id"],
            "evidence_region_id": evidence_location["texas_region_id"],
            "timezone": site["timezone"],
            "distance_km": rounded_distance,
            "proxy_quality": quality,
            "exact_cached_location_match": distance_km <= 0.01,
            "coordinate_verification_status": site["coordinate_verification"]["status"],
            "evidence_coordinates": {
                "latitude": float(evidence_location["latitude"]),
                "longitude": float(evidence_location["longitude"]),
            },
            "limitations": limitations,
        },
    }


def execute_recommendation(farm_profile: dict[str, Any]) -> dict[str, Any]:
    """Prepare, score, and validate one persistence-ready recommendation run."""
    prepared = prepare_recommendation_inputs(farm_profile)
    recommendation = score_crops(
        prepared["evidence_bundle"], prepared["farm_profile"], prepared["scoring_config"]
    )
    validate(recommendation, load_json(RECOMMENDATION_SCHEMA_PATH), "Recommendation output")
    engine_checks = validate_ranking_contract(recommendation)
    evidence_validation = prepared["evidence_bundle"]["validation"]
    errors: list[str] = []
    if evidence_validation.get("all_passed") is not True:
        errors.append("The EvidenceBundle did not pass required validation checks.")
    if engine_checks.get("eligibility_ranking_policy_passed") is not True:
        errors.append("The recommendation output failed deterministic ranking validation.")

    validation_report = {
        "report_version": "1.0.0",
        "report_schema_version": "1.0.0",
        "validator_version": "cropsage-ranking-validator-1.0.0",
        "status": "passed" if not errors else "rejected",
        "render_allowed": not errors,
        "profile_id": recommendation["profile_id"],
        "evidence_bundle_id": recommendation["evidence_bundle_id"],
        "scoring_version": recommendation["scoring_version"],
        "evidence_bundle_validation": evidence_validation,
        "engine_output_validation": engine_checks,
        "checks": [
            {
                "name": "evidence_bundle_valid",
                "passed": evidence_validation.get("all_passed") is True,
                "details": "The cached EvidenceBundle passed its finalized validation contract.",
            },
            {
                "name": "deterministic_ranking_valid",
                "passed": engine_checks.get("eligibility_ranking_policy_passed") is True,
                "details": "All 22 crop ranks, eligibility gates, and score caps were checked.",
            },
        ],
        "errors": errors,
        "warnings": prepared["location_resolution"]["limitations"],
    }
    return {
        "service_version": SERVICE_VERSION,
        "status": "validated" if not errors else "rejected",
        **prepared,
        "recommendation": recommendation,
        "validation_report": validation_report,
    }


def recommend_crops(
    *,
    latitude: float,
    longitude: float,
    planting_month: str,
    irrigation_availability: str,
    crop_id: str | None = None,
    soil_test_values: dict[str, Any] | None = None,
    irrigation_reliability: str | None = None,
    irrigation_method: str | None = None,
    location_label: str | None = None,
) -> dict[str, Any]:
    """Return deterministic crop rankings using the nearest cached Texas evidence.

    ``soil_test_values`` accepts ``ph`` plus ``tested_at`` and/or ``texture``.
    Optional provenance fields are ``laboratory_name``, ``report_reference``,
    ``texture_source``, and ``texture_observed_or_tested_at``.

    The frozen engine requires the scoring profile and EvidenceBundle to share
    coordinates. Consequently, the internal engine profile uses the selected
    cached site's coordinates. The response preserves the farmer's true input
    and reports the proxy distance; provider evidence is never relabelled.
    """
    farmer_latitude, farmer_longitude = _validate_farmer_location(latitude, longitude)
    if not isinstance(planting_month, str) or not PLANTING_MONTH_PATTERN.fullmatch(planting_month):
        raise RecommendationServiceError("planting_month must use YYYY-MM format")
    if crop_id is not None and (not isinstance(crop_id, str) or not crop_id.strip()):
        raise RecommendationServiceError("crop_id must be a non-empty crop identifier or null")
    requested_crop_id = crop_id.strip() if crop_id is not None else None

    site, evidence_path, distance_km = _resolve_cached_site(farmer_latitude, farmer_longitude)
    evidence = load_json(evidence_path)
    validate(evidence, load_json(EVIDENCE_SCHEMA_PATH), "Cached EvidenceBundle")
    config = load_json(CONFIG_PATH)
    if config.get("scoring_version") != REQUIRED_SCORING_VERSION:
        raise RecommendationServiceError(
            f"Recommendation service requires scoring engine {REQUIRED_SCORING_VERSION}; "
            f"found {config.get('scoring_version')}"
        )

    available_crop_ids = set(evidence["catalog"]["crop_ids"])
    if requested_crop_id is not None and requested_crop_id not in available_crop_ids:
        raise RecommendationServiceError(
            f"Unknown crop_id {requested_crop_id!r}; expected one of {', '.join(sorted(available_crop_ids))}"
        )

    irrigation = _irrigation_profile(
        irrigation_availability,
        irrigation_reliability,
        irrigation_method,
    )
    soil_overrides = _soil_overrides(soil_test_values)
    farmer_request = {
        "location": {
            "latitude": farmer_latitude,
            "longitude": farmer_longitude,
            "location_label": location_label,
        },
        "planting_month": planting_month,
        "irrigation": irrigation,
        "requested_crop_id": requested_crop_id,
        "soil_test_values": soil_test_values,
    }
    evidence_location = evidence["location"]
    profile: dict[str, Any] = {
        "schema_version": "1.0.0",
        "profile_id": _profile_id(farmer_request),
        "location": {
            "latitude": float(evidence_location["latitude"]),
            "longitude": float(evidence_location["longitude"]),
            "farm_name": evidence_location["farm_name"],
            "location_label": site["nearby_agricultural_center"],
            "source": "demo_farm",
        },
        "planting": {"planned_month": planting_month, "flexibility_days": None},
        "requested_crop_id": requested_crop_id,
        "irrigation": irrigation,
    }
    if soil_overrides is not None:
        profile["soil_overrides"] = soil_overrides
    validate(profile, load_json(FARM_PROFILE_SCHEMA_PATH), "Generated farm profile")

    recommendation = score_crops(evidence, profile, config)
    validate(recommendation, load_json(RECOMMENDATION_SCHEMA_PATH), "Recommendation output")
    rounded_distance = round(distance_km, 2)
    quality = _proxy_quality(distance_km)
    limitations = [
        "Texas membership currently uses a coarse coordinate envelope, not an official state-boundary polygon.",
        "Provider evidence comes from the nearest cached representative site, not the farmer's exact parcel.",
        "Use live location-specific provider collection before treating the result as field-specific advice.",
    ]
    if quality == "distant_proxy":
        limitations.append("The nearest cached site is more than 150 km away; treat this result as exploratory only.")

    return {
        "service_version": SERVICE_VERSION,
        "result_type": "recommendation",
        "status": "validated",
        "request": farmer_request,
        "location_resolution": {
            "method": "nearest_cached_representative_site",
            "site_id": site["site_id"],
            "site_name": site["name"],
            "parent_catalog_region_id": site["parent_region_id"],
            "evidence_region_id": evidence_location["texas_region_id"],
            "timezone": site["timezone"],
            "distance_km": rounded_distance,
            "proxy_quality": quality,
            "exact_cached_location_match": distance_km <= 0.01,
            "coordinate_verification_status": site["coordinate_verification"]["status"],
            "evidence_coordinates": {
                "latitude": float(evidence_location["latitude"]),
                "longitude": float(evidence_location["longitude"]),
            },
            "limitations": limitations,
        },
        "recommendation": recommendation,
        "confidence_context": {
            "metric_name": "evidence_confidence",
            "farmer_label": "evidence strength",
            "explanation": (
                "This measures how much reliable evidence was available for the requested time and place; "
                "it does not measure crop suitability. Long-range plans cannot use short-range live weather "
                "signals, so evidence confidence is intentionally conservative."
            ),
            "display_bands": {"high": "strong", "medium": "moderate", "low": "limited"},
        },
    }


def get_planting_guidance(
    *,
    latitude: float,
    longitude: float,
    crop_id: str,
    location_label: str | None = None,
) -> dict[str, Any]:
    """Return catalog planting-window guidance without requiring a year or irrigation."""
    farmer_latitude, farmer_longitude = _validate_farmer_location(latitude, longitude)
    if not isinstance(crop_id, str) or not crop_id.strip():
        raise RecommendationServiceError("A crop is required for planting-window guidance")
    requested_crop_id = crop_id.strip()
    site, evidence_path, distance_km = _resolve_cached_site(farmer_latitude, farmer_longitude)
    evidence = load_json(evidence_path)
    validate(evidence, load_json(EVIDENCE_SCHEMA_PATH), "Cached EvidenceBundle")
    crop = next(
        (item for item in evidence.get("crop_evidence", []) if item.get("crop_id") == requested_crop_id),
        None,
    )
    if crop is None:
        raise RecommendationServiceError(f"Unknown crop_id {requested_crop_id!r}")
    profile = crop["profile"]
    rating = profile["regional_suitability"]
    return {
        "service_version": SERVICE_VERSION,
        "result_type": "planting_guidance",
        "status": "validated",
        "request": {
            "location": {
                "latitude": farmer_latitude,
                "longitude": farmer_longitude,
                "location_label": location_label,
            },
            "requested_crop_id": requested_crop_id,
        },
        "location_resolution": {
            "site_id": site["site_id"],
            "site_name": site["name"],
            "parent_catalog_region_id": site["parent_region_id"],
            "distance_km": round(distance_km, 2),
            "proxy_quality": _proxy_quality(distance_km),
        },
        "guidance": {
            "crop_id": crop["crop_id"],
            "crop_name": crop["crop_name"],
            "regionally_eligible": crop["regionally_eligible"],
            "regional_rating": rating["rating"],
            "regional_basis": rating["basis"],
            "planting_windows": profile["planting_windows"],
            "planting_window_evidence_status": profile["planting_window_evidence_status"],
            "planting_window_basis": profile["planting_window_basis"],
            "days_to_maturity": profile.get("days_to_maturity"),
            "frost_sensitivity": profile.get("frost_sensitivity"),
        },
    }
