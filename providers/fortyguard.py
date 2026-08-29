"""FortyGuard heat collector with resumable activity checkpoints."""

from __future__ import annotations

import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import requests

from .common import (
    ROOT,
    FetchOutcome,
    LocationTarget,
    ProviderCollectionError,
    cached_artifact,
    canonical_hash,
    default_provider_directory,
    load_json,
    utc_now,
    write_json_atomic,
)


DEFAULT_BASE_URL = "https://api.fortyguard.com"
SUCCESS_STATUSES = {"completed", "succeeded"}
FAILURE_STATUSES = {"failed", "error"}
SCOREABLE_THRESHOLD_USE = "soft_penalty"


class FortyGuardHttpClient:
    """Small HTTP client exposing submit and poll separately for safe resume."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        request_timeout: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        key = api_key or os.getenv("FORTYGUARD_API_KEY")
        if not key:
            raise ProviderCollectionError(
                "FORTYGUARD_API_KEY is required for a live FortyGuard collection"
            )
        self.base_url = (base_url or os.getenv("FORTYGUARD_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.request_timeout = request_timeout
        self.session = session or requests.Session()
        self.session.headers.update({"api-key": key, "Content-Type": "application/json"})

    def submit_heatmap(self, payload: dict[str, Any]) -> str:
        response = self.session.post(
            f"{self.base_url}/v1/heatmap",
            json=payload,
            timeout=self.request_timeout,
        )
        if not response.ok:
            raise ProviderCollectionError(
                f"FortyGuard submission failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        body = response.json()
        try:
            return str(body["data"]["activity_id"])
        except (KeyError, TypeError) as exc:
            raise ProviderCollectionError(f"Unexpected FortyGuard submission response: {body}") from exc

    def wait_for(
        self,
        activity_id: str,
        *,
        poll_interval: float = 3.0,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            response = self.session.get(
                f"{self.base_url}/v1/status/{activity_id}",
                timeout=self.request_timeout,
            )
            if response.status_code == 404:
                status = "pending"
            elif not response.ok:
                raise ProviderCollectionError(
                    f"FortyGuard status failed with HTTP {response.status_code}: {response.text[:300]}"
                )
            else:
                body = response.json()
                data = body.get("data", body)
                status = str(data.get("status", "")).lower()
                if status in SUCCESS_STATUSES:
                    result = data.get("result", data)
                    if not isinstance(result, dict):
                        raise ProviderCollectionError("FortyGuard completed without an object result")
                    return result
                if status in FAILURE_STATUSES:
                    raise ProviderCollectionError(
                        f"FortyGuard activity {activity_id} failed: {data.get('message') or data}"
                    )
            if time.monotonic() >= deadline:
                raise ProviderCollectionError(
                    f"FortyGuard activity {activity_id} is still {status!r} after {timeout:.0f}s; "
                    "rerun the collector to continue polling the same checkpointed activity"
                )
            time.sleep(poll_interval)


def point_square_aoi(latitude: float, longitude: float, side_m: float = 1000.0) -> dict[str, Any]:
    """Return an approximately square GeoJSON polygon centered on a farm point."""
    half = side_m / 2.0
    lat_delta = half / 111_320.0
    lon_delta = half / (111_320.0 * math.cos(math.radians(latitude)))
    west, east = longitude - lon_delta, longitude + lon_delta
    south, north = latitude - lat_delta, latitude + lat_delta
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south]
        ]],
    }


def _scoreable_thresholds(catalog: dict[str, Any]) -> list[float]:
    values = {
        float(crop["heat_stress_threshold"]["value_c"])
        for crop in catalog["crops"]
        if crop.get("heat_stress_threshold", {}).get("value_c") is not None
        and crop.get("heat_stress_threshold", {}).get("scoring_use") == SCOREABLE_THRESHOLD_USE
    }
    return sorted(values)


def _payload(
    polygon: dict[str, Any],
    start: date,
    end: date,
    granularity_m: int,
    analytic_type: str,
    threshold: float | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "polygon_aoi": polygon,
        "date_time": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "filter_type": 4,
        },
        "granularity": granularity_m,
        "analytic_type": analytic_type,
    }
    if threshold is not None:
        value.update({"threshold": threshold, "direction": "above"})
    return value


def _checkpointed_request(
    client: Any,
    payload: dict[str, Any],
    checkpoint_dir: Path,
    *,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    key = canonical_hash(payload)[:20]
    path = checkpoint_dir / f"{payload['analytic_type']}_{key}.json"
    checkpoint = load_json(path) if path.exists() else None
    if checkpoint and checkpoint.get("request") != payload:
        checkpoint = None
    if checkpoint and isinstance(checkpoint.get("result"), dict):
        return {
            "activity_id": checkpoint["activity_id"],
            "result": checkpoint["result"],
            "source": "request_checkpoint",
        }
    if checkpoint and checkpoint.get("activity_id"):
        activity_id = str(checkpoint["activity_id"])
    else:
        activity_id = str(client.submit_heatmap(payload))
        write_json_atomic(
            path,
            {
                "request": payload,
                "activity_id": activity_id,
                "status": "submitted",
                "submitted_at": utc_now().isoformat(),
            },
        )
    result = client.wait_for(
        activity_id,
        poll_interval=poll_interval,
        timeout=timeout,
    )
    write_json_atomic(
        path,
        {
            "request": payload,
            "activity_id": activity_id,
            "status": "completed",
            "completed_at": utc_now().isoformat(),
            "result": result,
        },
    )
    return {"activity_id": activity_id, "result": result, "source": "live_or_resumed"}


def _feature_values(response: dict[str, Any], analytic_type: str) -> list[float]:
    features = response.get("result", {}).get("map_data", {}).get("features", [])
    if not features:
        raise ProviderCollectionError(f"FortyGuard {analytic_type} response has no map tiles")
    key = "average_temperature" if analytic_type == "tcm" else "value"
    values = []
    for feature in features:
        raw = feature.get("properties", {}).get(key)
        if raw is None:
            raise ProviderCollectionError(f"FortyGuard {analytic_type} response contains a null {key}")
        number = float(raw)
        if not math.isfinite(number):
            raise ProviderCollectionError(f"FortyGuard {analytic_type} response contains an invalid number")
        values.append(number)
    return values


def _tcm_period_temperature_range(response: dict[str, Any]) -> tuple[float, float]:
    """Return the temporal temperature range exposed inside the TCM tiles.

    ``temperature_stats.minimum`` and ``maximum`` describe the spatial range of
    ``average_temperature`` across tiles.  The per-tile ``min_temperature`` and
    ``max_temperature`` properties describe the modeled period extremes.
    """
    features = response.get("result", {}).get("map_data", {}).get("features", [])
    minimums: list[float] = []
    maximums: list[float] = []
    for feature in features:
        properties = feature.get("properties", {})
        for key, values in (
            ("min_temperature", minimums),
            ("max_temperature", maximums),
        ):
            raw = properties.get(key)
            if raw is None:
                raise ProviderCollectionError(
                    f"FortyGuard TCM response contains a null {key}"
                )
            number = float(raw)
            if not math.isfinite(number):
                raise ProviderCollectionError(
                    f"FortyGuard TCM response contains an invalid {key}"
                )
            values.append(number)
    if not minimums or not maximums:
        raise ProviderCollectionError("FortyGuard TCM response has no temperature ranges")
    return min(minimums), max(maximums)


def _request_validation(
    response: dict[str, Any], analytic_type: str, threshold: float | None
) -> dict[str, Any]:
    values = _feature_values(response, analytic_type)
    return {
        "analytic_type": analytic_type,
        "threshold_c": threshold,
        "activity_id": response["activity_id"],
        "source": response["source"],
        "tile_count": len(values),
        "numeric_count": len(values),
        "null_count": 0,
        "min": min(values),
        "mean": fmean(values),
        "max": max(values),
        "unique_values": len(set(values)),
        "reported_units": response["result"].get("stats_data", {}).get("units"),
    }


def _temperature_fit(mean_c: float, minimum: float, maximum: float) -> tuple[str, float]:
    if minimum <= mean_c <= maximum:
        return "within_optimal_mean", 0.0
    if mean_c < minimum:
        return "below_optimal_mean", minimum - mean_c
    return "above_optimal_mean", mean_c - maximum


def _crop_results(
    catalog: dict[str, Any],
    region_id: str,
    mean_c: float,
    period_min_c: float,
    period_max_c: float,
    threshold_by_value: dict[float, dict[str, Any]],
    window_hours: int,
) -> list[dict[str, Any]]:
    rows = []
    for crop in catalog["crops"]:
        optimum = crop["optimal_temperature_range"]
        low = float(optimum.get("min", optimum.get("min_c")))
        high = float(optimum.get("max", optimum.get("max_c")))
        fit, distance = _temperature_fit(mean_c, low, high)
        threshold = crop.get("heat_stress_threshold", {})
        threshold_c = threshold.get("value_c")
        scoring_use = threshold.get("scoring_use", "not_available")
        evidence_status = threshold.get("evidence_status", "not_available")
        scoreable = scoring_use == SCOREABLE_THRESHOLD_USE and threshold_c is not None
        threshold_result = threshold_by_value.get(float(threshold_c)) if scoreable else None
        eligible = region_id in crop.get("supported_texas_regions", [])
        exceedance = threshold_result.get("exceedance_hours") if threshold_result else None
        persistence = threshold_result.get("persistence_hours") if threshold_result else None
        if not eligible:
            action = "excluded_for_region"
        elif not scoreable:
            action = "no_scoreable_threshold_do_not_invent"
        elif exceedance == 0:
            action = "no_threshold_exceedance"
        else:
            action = "soft_penalty_candidate"
        rows.append(
            {
                "crop_id": crop["crop_id"],
                "crop": crop["common_name"],
                "regionally_eligible": eligible,
                "optimal_min_c": low,
                "optimal_max_c": high,
                "period_mean_c": mean_c,
                "period_min_c": period_min_c,
                "period_max_c": period_max_c,
                "temperature_fit": fit,
                "distance_from_optimum_c": distance,
                "heat_threshold_c": threshold_c,
                "threshold_scoring_use": scoring_use,
                "threshold_evidence_status": evidence_status,
                "exceedance_hours": exceedance,
                "persistence_hours": persistence,
                "exceedance_fraction_of_window": (
                    None if exceedance is None else exceedance / window_hours
                ),
                "heat_action": action,
                "catalog_confidence": crop["confidence"],
            }
        )
    return rows


def fetch_fortyguard(
    location: LocationTarget,
    *,
    output_path: Path | None = None,
    catalog_path: Path | None = None,
    client: Any | None = None,
    polygon_aoi: dict[str, Any] | None = None,
    end_date: date | None = None,
    window_days: int = 7,
    granularity_m: int = 100,
    poll_interval: float = 3.0,
    activity_timeout: float = 600.0,
    max_age_hours: float = 168.0,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> FetchOutcome:
    """Collect one TCM window and scoreable threshold analyses using filter 4."""
    if window_days < 1:
        raise ValueError("window_days must be positive")
    if granularity_m not in {60, 80, 100}:
        raise ValueError("FortyGuard granularity must be 60, 80, or 100 metres")
    output = output_path or default_provider_directory(location) / "fortyguard.json"
    reference = (now or utc_now()).astimezone(timezone.utc)
    cached = cached_artifact(
        output,
        max_age_hours=max_age_hours,
        now=reference,
        force_refresh=force_refresh,
    )
    if cached is not None:
        return FetchOutcome("fortyguard", cached, output, "fresh_cache")

    catalog = load_json(catalog_path or ROOT / "data" / "crop-catalog" / "catalog.json")
    if len(catalog["crops"]) != 22:
        raise ProviderCollectionError("Crop catalog must contain exactly 22 crops")
    thresholds = _scoreable_thresholds(catalog)
    period_end = end_date or (reference.date() - timedelta(days=1))
    period_start = period_end - timedelta(days=window_days - 1)
    polygon = polygon_aoi or point_square_aoi(location.latitude, location.longitude)
    api = client or FortyGuardHttpClient()
    checkpoint_dir = output.parent / "fortyguard_requests"

    responses: list[tuple[str, float | None, dict[str, Any]]] = []
    tcm = _checkpointed_request(
        api,
        _payload(polygon, period_start, period_end, granularity_m, "tcm"),
        checkpoint_dir,
        poll_interval=poll_interval,
        timeout=activity_timeout,
    )
    responses.append(("tcm", None, tcm))
    threshold_results = []
    for threshold in thresholds:
        pair: dict[str, dict[str, Any]] = {}
        for analytic_type in ("exceedance", "persistence"):
            response = _checkpointed_request(
                api,
                _payload(
                    polygon,
                    period_start,
                    period_end,
                    granularity_m,
                    analytic_type,
                    threshold,
                ),
                checkpoint_dir,
                poll_interval=poll_interval,
                timeout=activity_timeout,
            )
            pair[analytic_type] = response
            responses.append((analytic_type, threshold, response))
        exceedance_values = _feature_values(pair["exceedance"], "exceedance")
        persistence_values = _feature_values(pair["persistence"], "persistence")
        threshold_results.append(
            {
                "threshold_c": threshold,
                "exceedance_hours": fmean(exceedance_values),
                "persistence_hours": fmean(persistence_values),
                "exceedance_min": min(exceedance_values),
                "exceedance_max": max(exceedance_values),
                "persistence_min": min(persistence_values),
                "persistence_max": max(persistence_values),
                "exceedance_activity_id": pair["exceedance"]["activity_id"],
                "persistence_activity_id": pair["persistence"]["activity_id"],
            }
        )

    validation_rows = [
        _request_validation(response, analytic_type, threshold)
        for analytic_type, threshold, response in responses
    ]
    tile_counts = {row["tile_count"] for row in validation_rows}
    if len(tile_counts) != 1:
        raise ProviderCollectionError(f"FortyGuard tile counts disagree: {sorted(tile_counts)}")
    tcm_values = _feature_values(tcm, "tcm")
    minimum_tile_average_c = min(tcm_values)
    maximum_tile_average_c = max(tcm_values)
    period_minimum_c, period_maximum_c = _tcm_period_temperature_range(tcm)
    mean_c = fmean(tcm_values)
    threshold_by_value = {row["threshold_c"]: row for row in threshold_results}
    crop_rows = _crop_results(
        catalog,
        location.texas_region_id,
        mean_c,
        period_minimum_c,
        period_maximum_c,
        threshold_by_value,
        window_days * 24,
    )
    eligible_count = sum(row["regionally_eligible"] for row in crop_rows)
    period_summary = {
        "window_name": "one_week" if window_days == 7 else f"{window_days}_days",
        "window_days": window_days,
        "window_start": period_start.isoformat(),
        "window_end": period_end.isoformat(),
        "catalog_crop_count": 22,
        "regionally_eligible_count": eligible_count,
        "numeric_threshold_crop_count": sum(
            crop.get("heat_stress_threshold", {}).get("value_c") is not None
            for crop in catalog["crops"]
        ),
        "unique_threshold_count": len(thresholds),
        "request_count": len(responses),
        "tile_count": tile_counts.pop(),
        "null_values_across_requests": 0,
        "mean_temperature_c": mean_c,
        "minimum_tile_average_temperature_c": minimum_tile_average_c,
        "maximum_tile_average_temperature_c": maximum_tile_average_c,
        "period_minimum_temperature_c": period_minimum_c,
        "period_maximum_temperature_c": period_maximum_c,
        "peak_hour_raw": None,
        "peak_hour_timezone_status": "not_collected_for_mvp",
        "granularity_m": granularity_m,
    }
    test_id = "test_one_week" if window_days == 7 else f"test_{window_days}_days"
    test = {
        "period_summary": period_summary,
        "request_validation": validation_rows,
        "threshold_results": threshold_results,
        "crop_results": crop_rows,
    }
    artifact = {
        "artifact": "CropSage FortyGuard location heat evidence",
        "schema_version": "1.0",
        "generated_at_utc": reference.isoformat(),
        "farm": {
            "farm_id": location.farm_id,
            "name": location.farm_name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "region_id": location.texas_region_id,
            "timezone": location.timezone,
            "granularity_m": granularity_m,
            "polygon_aoi": polygon,
        },
        "collection_policy": {
            "filter_type": 4,
            "window_days": window_days,
            "threshold_rule": "unique soft_penalty thresholds only",
            "aggregation": "unweighted arithmetic mean across returned tiles",
            "time_of_measure": "not collected for MVP",
        },
        "validation": {
            "test_count": 1,
            "catalog_crop_count_per_test": 22,
            "response_count_per_test": len(responses),
            "total_validated_responses": len(responses),
            "tile_count_per_response": period_summary["tile_count"],
            "total_null_values": 0,
            "unique_numeric_thresholds": len(thresholds),
            "peak_hour_timezone_status": "not_collected_for_mvp",
        },
        "period_comparison": [period_summary],
        "threshold_comparison": [
            {
                "threshold_c": row["threshold_c"],
                "windows": [{
                    "test_id": test_id,
                    "window_days": window_days,
                    "window_hours": window_days * 24,
                    "exceedance_hours": row["exceedance_hours"],
                    "exceedance_fraction": row["exceedance_hours"] / (window_days * 24),
                    "persistence_hours": row["persistence_hours"],
                    "exceedance_activity_id": row["exceedance_activity_id"],
                    "persistence_activity_id": row["persistence_activity_id"],
                }],
            }
            for row in threshold_results
        ],
        "crop_comparison": crop_rows,
        "tests": {test_id: test},
    }
    write_json_atomic(output, artifact)
    return FetchOutcome("fortyguard", artifact, output, "live")
