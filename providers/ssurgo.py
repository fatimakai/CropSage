"""USDA NRCS SSURGO point collector via Soil Data Access."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .common import (
    ROOT,
    FetchOutcome,
    LocationTarget,
    ProviderCollectionError,
    cached_artifact,
    default_provider_directory,
    load_json,
    safe_response_json,
    utc_now,
    write_json_atomic,
)


SDA_ENDPOINT = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"
TOPSOIL_DEPTH_CM = 30.0
FALLBACK_ROOT_LIMIT_CM = 150.0
NUMERIC_FIELDS = {
    "comppct_r",
    "restrictive_depth_cm",
    "hzdept_r",
    "hzdepb_r",
    "awc_r",
    "ph1to1h2o_r",
    "sandtotal_r",
    "silttotal_r",
    "claytotal_r",
}
TEXTURE_CODE_TO_NAME = {
    "S": "sand",
    "LS": "loamy sand",
    "LFS": "loamy fine sand",
    "SL": "sandy loam",
    "FSL": "fine sandy loam",
    "L": "loam",
    "SIL": "silt loam",
    "SI": "silt",
    "SCL": "sandy clay loam",
    "CL": "clay loam",
    "SICL": "silty clay loam",
    "SC": "sandy clay",
    "SIC": "silty clay",
    "C": "clay",
}


def build_point_soil_query(latitude: float, longitude: float) -> str:
    point = f"POINT({longitude:.8f} {latitude:.8f})"
    return f"""
SELECT
  l.areasymbol,
  sac.saverest,
  mu.mukey,
  mu.musym,
  mu.muname,
  mu.farmlndcl,
  co.cokey,
  co.compname,
  co.comppct_r,
  co.majcompflag,
  co.drainagecl,
  co.hydricrating,
  cr.restrictive_depth_cm,
  ch.chkey,
  ch.hzname,
  ch.hzdept_r,
  ch.hzdepb_r,
  ch.awc_r,
  ch.ph1to1h2o_r,
  ch.sandtotal_r,
  ch.silttotal_r,
  ch.claytotal_r,
  tx.texture
FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{point}') AS p
JOIN mapunit AS mu ON mu.mukey = p.mukey
JOIN legend AS l ON l.lkey = mu.lkey
LEFT JOIN sacatalog AS sac ON sac.areasymbol = l.areasymbol
JOIN component AS co ON co.mukey = mu.mukey
LEFT JOIN (
  SELECT cokey, MIN(resdept_r) AS restrictive_depth_cm
  FROM corestrictions
  WHERE resdept_r IS NOT NULL
  GROUP BY cokey
) AS cr ON cr.cokey = co.cokey
JOIN chorizon AS ch ON ch.cokey = co.cokey
LEFT JOIN chtexturegrp AS tx
  ON tx.chkey = ch.chkey AND tx.rvindicator = 'Yes'
WHERE co.majcompflag = 'Yes'
ORDER BY co.comppct_r DESC, co.cokey, ch.hzdept_r
""".strip()


def _number(value: Any) -> float | None:
    if value in (None, "", "NULL", "null"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    table = payload.get("Table")
    if not isinstance(table, list) or len(table) < 2:
        raise ProviderCollectionError("SSURGO returned no table rows for this point")
    headers = [str(value).lower() for value in table[0]]
    rows = []
    for values in table[1:]:
        row = dict(zip(headers, values))
        for field in NUMERIC_FIELDS:
            row[field] = _number(row.get(field))
        rows.append(row)
    return rows


def _overlap(top: float, bottom: float, start: float, end: float) -> float:
    return max(0.0, min(bottom, end) - max(top, start))


def _weighted_mean(
    horizons: list[dict[str, Any]], field: str, depth_cm: float
) -> tuple[float | None, float]:
    total = 0.0
    coverage = 0.0
    for row in horizons:
        value = row.get(field)
        top = row.get("hzdept_r")
        bottom = row.get("hzdepb_r")
        if value is None or top is None or bottom is None:
            continue
        thickness = _overlap(float(top), float(bottom), 0.0, depth_cm)
        total += float(value) * thickness
        coverage += thickness
    return (total / coverage if coverage else None), coverage


def _available_water(
    horizons: list[dict[str, Any]], depth_cm: float
) -> tuple[float | None, float]:
    total = 0.0
    coverage = 0.0
    for row in horizons:
        awc = row.get("awc_r")
        top = row.get("hzdept_r")
        bottom = row.get("hzdepb_r")
        if awc is None or top is None or bottom is None:
            continue
        thickness = _overlap(float(top), float(bottom), 0.0, depth_cm)
        total += float(awc) * thickness * 10.0
        coverage += thickness
    return (total if coverage else None), coverage


def _canonical_texture(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).lower().replace("-", " ").strip()
    for qualifier in ("well drained ", "light textured ", "deep "):
        if text.startswith(qualifier):
            text = text[len(qualifier):]
    return " ".join(text.split())


def _ph_fit(value: float | None, requirement: dict[str, Any]) -> str:
    if value is None:
        return "unknown"
    if value < float(requirement["min"]):
        return "below range"
    if value > float(requirement["max"]):
        return "above range"
    return "within range"


def _drainage_fit(actual: str | None, requirement: str) -> str:
    if not actual:
        return "unknown"
    rank = {
        "very poorly drained": 0,
        "poorly drained": 1,
        "somewhat poorly drained": 2,
        "moderately well drained": 3,
        "well drained": 4,
        "somewhat excessively drained": 5,
        "excessively drained": 6,
    }.get(actual.lower())
    if rank is None:
        return "review"
    if requirement == "poorly_drained_tolerant":
        return "compatible"
    if requirement == "moderate":
        return "compatible" if 2 <= rank <= 4 else "review"
    if requirement == "well_drained":
        return "compatible" if rank >= 3 else "likely mismatch"
    if requirement == "very_well_drained":
        return "compatible" if rank >= 4 else "likely mismatch"
    return "review"


def _range_text(minimum: float | None, maximum: float | None, digits: int = 1) -> str | None:
    if minimum is None or maximum is None:
        return None
    return f"{minimum:.{digits}f}-{maximum:.{digits}f}"


def _summarize(
    rows: list[dict[str, Any]], location: LocationTarget
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    components: dict[str, float] = {}
    for row in rows:
        key = str(row.get("cokey"))
        percentage = row.get("comppct_r")
        components[key] = float(percentage) if percentage is not None else -1.0
    dominant = max(components, key=components.get)
    horizons_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("cokey")) == dominant:
            horizons_by_key[str(row.get("chkey"))] = row
    horizons = sorted(
        horizons_by_key.values(),
        key=lambda row: float(row.get("hzdept_r") or 0),
    )
    if not horizons:
        raise ProviderCollectionError("SSURGO returned no horizons for the dominant component")
    first = horizons[0]
    texture_code = str(first.get("texture") or "").strip().upper() or None
    texture = TEXTURE_CODE_TO_NAME.get(
        texture_code,
        texture_code.lower() if texture_code else None,
    )
    ph, ph_coverage = _weighted_mean(horizons, "ph1to1h2o_r", TOPSOIL_DEPTH_CM)
    restrictions = [
        float(row["restrictive_depth_cm"])
        for row in horizons
        if row.get("restrictive_depth_cm") is not None
    ]
    if restrictions:
        root_limit = min(restrictions)
        root_basis = "shallowest SSURGO component restriction"
    else:
        root_limit = FALLBACK_ROOT_LIMIT_CM
        root_basis = "SSURGO reported no restriction; gSSURGO 150 cm fallback"
    water, water_coverage = _available_water(horizons, root_limit)
    required = {
        "muname": first.get("muname"),
        "farmlndcl": first.get("farmlndcl"),
        "drainagecl": first.get("drainagecl"),
        "hydricrating": first.get("hydricrating"),
        "surface_texture": texture,
        "surface_sand_percent": first.get("sandtotal_r"),
        "surface_silt_percent": first.get("silttotal_r"),
        "surface_clay_percent": first.get("claytotal_r"),
        "mapped_ph": ph,
        "water": water,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise ProviderCollectionError(f"SSURGO dominant component is missing: {missing}")
    summary = {
        "source": "USDA NRCS SSURGO via Soil Data Access",
        "query_latitude": location.latitude,
        "query_longitude": location.longitude,
        "survey_area_symbol": first.get("areasymbol"),
        "survey_data_saved": first.get("saverest"),
        "map_unit_key": first.get("mukey"),
        "map_unit_symbol": first.get("musym"),
        "map_unit_name": first.get("muname"),
        "farmland_classification": first.get("farmlndcl"),
        "dominant_component": first.get("compname"),
        "dominant_component_percent": first.get("comppct_r"),
        "surface_texture_code": texture_code,
        "surface_texture": texture,
        "surface_sand_percent": first.get("sandtotal_r"),
        "surface_silt_percent": first.get("silttotal_r"),
        "surface_clay_percent": first.get("claytotal_r"),
        "mapped_ph_0_30cm": round(float(ph), 2),
        "ph_depth_coverage_cm": round(ph_coverage, 1),
        "drainage_class": first.get("drainagecl"),
        "hydric_rating": first.get("hydricrating"),
        "soil_root_limit_cm": round(root_limit, 1),
        "soil_root_limit_basis": root_basis,
        "available_water_mm_to_soil_limit": round(float(water), 1),
        "available_water_depth_coverage_cm": round(water_coverage, 1),
    }
    return summary, horizons


def _crop_comparisons(
    catalog: dict[str, Any],
    summary: dict[str, Any],
    horizons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    texture = _canonical_texture(summary["surface_texture"])
    mapped_ph = float(summary["mapped_ph_0_30cm"])
    soil_limit = float(summary["soil_root_limit_cm"])
    comparisons = []
    for crop in catalog["crops"]:
        preferred = {_canonical_texture(item) for item in crop["preferred_soil_textures"]}
        depth = crop["effective_root_zone_depth_cm"]
        usable_min = min(float(depth["min"]), soil_limit)
        usable_max = min(float(depth["max"]), soil_limit)
        storage_min, coverage_min = _available_water(horizons, usable_min)
        storage_max, coverage_max = _available_water(horizons, usable_max)
        comparisons.append(
            {
                "crop_id": crop["crop_id"],
                "crop": crop["common_name"],
                "SSURGO_texture": texture,
                "texture_fit": "preferred" if texture in preferred else "not listed as preferred",
                "mapped_pH": mapped_ph,
                "catalog_pH_range": f"{crop['ph_tolerable_range']['min']}-{crop['ph_tolerable_range']['max']}",
                "pH_fit": _ph_fit(mapped_ph, crop["ph_tolerable_range"]),
                "SSURGO_drainage": summary["drainage_class"],
                "drainage_fit": _drainage_fit(
                    summary["drainage_class"],
                    crop["drainage_requirement"]["class"],
                ),
                "catalog_root_zone_cm": f"{depth['min']}-{depth['max']}",
                "soil_root_limit_cm": soil_limit,
                "usable_root_zone_cm": _range_text(usable_min, usable_max, 0),
                "accessible_water_storage_mm": _range_text(storage_min, storage_max),
                "water_storage_coverage_cm": _range_text(coverage_min, coverage_max, 0),
                "water_use_rule": "storage context only; not rainfall or irrigation supply",
            }
        )
    return comparisons


def fetch_ssurgo(
    location: LocationTarget,
    *,
    output_path: Path | None = None,
    catalog_path: Path | None = None,
    session: requests.Session | None = None,
    timeout: float = 60.0,
    max_age_hours: float = 8760.0,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> FetchOutcome:
    """Fetch the dominant SSURGO component and build 22 crop comparisons."""
    output = output_path or default_provider_directory(location) / "ssurgo.json"
    reference = (now or utc_now()).astimezone(timezone.utc)
    cached = cached_artifact(
        output,
        max_age_hours=max_age_hours,
        now=reference,
        force_refresh=force_refresh,
    )
    if cached is not None:
        return FetchOutcome("ssurgo", cached, output, "fresh_cache")
    catalog = load_json(catalog_path or ROOT / "data" / "crop-catalog" / "catalog.json")
    query = build_point_soil_query(location.latitude, location.longitude)
    http = session or requests.Session()
    response = http.post(
        SDA_ENDPOINT,
        json={"query": query, "format": "JSON+COLUMNNAME"},
        timeout=timeout,
    )
    payload = safe_response_json(response, "USDA Soil Data Access")
    raw_rows = _parse_rows(payload)
    summary, horizons = _summarize(raw_rows, location)
    comparisons = _crop_comparisons(catalog, summary, horizons)
    if len(comparisons) != 22:
        raise ProviderCollectionError("SSURGO comparison did not cover all 22 crops")
    artifact = {
        "schema_version": "1.0",
        "provider": "USDA NRCS SSURGO via Soil Data Access",
        "status": "validated",
        "generated_at": reference.isoformat(),
        "farm": {
            **location.provider_farm(include_timezone=False),
            "crop_region": location.texas_region_id,
        },
        "source": {
            "endpoint": SDA_ENDPOINT,
            "format": "JSON+COLUMNNAME",
            "lookup_function": "SDA_Get_Mukey_from_intersection_with_WktWgs84",
            "query_version": "cropsage-point-soil-v1",
        },
        "interpretation": {
            "evidence_role": "mapped permanent soil properties and available-water storage capacity",
            "spatial_warning": "Mapped point evidence for a dominant SSURGO component; not an on-farm sample or laboratory measurement.",
            "measurement_warning": "SSURGO is mapped survey evidence, not a field or laboratory measurement.",
            "water_warning": "Available-water capacity is storage context, not current soil moisture, rainfall, irrigation, or seasonal supply.",
            "override_rule": "Valid farmer measurements or laboratory soil tests override mapped values while preserving both sources.",
        },
        "soil_summary": summary,
        "dominant_component_horizons": horizons,
        "crop_comparisons": comparisons,
        "quality": {
            "catalog_version": catalog["catalog_version"],
            "catalog_crop_count": len(catalog["crops"]),
            "comparison_count": len(comparisons),
            "raw_horizon_count": len(raw_rows),
            "dominant_horizon_count": len(horizons),
            "dominant_component_percent": summary["dominant_component_percent"],
            "ph_depth_coverage_cm": summary["ph_depth_coverage_cm"],
            "available_water_depth_coverage_cm": summary["available_water_depth_coverage_cm"],
        },
    }
    write_json_atomic(output, artifact)
    return FetchOutcome("ssurgo", artifact, output, "live")
