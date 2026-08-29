"""Open-Meteo collector for current, recent, forecast, and modeled soil evidence."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .common import (
    FetchOutcome,
    LocationTarget,
    ProviderCollectionError,
    cached_artifact,
    default_provider_directory,
    safe_response_json,
    utc_now,
    write_json_atomic,
)


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "weather_code",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
)
HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "precipitation_probability",
    "et0_fao_evapotranspiration",
    "vapour_pressure_deficit",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
)
DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "precipitation_probability_max",
    "et0_fao_evapotranspiration",
)
SOIL_MOISTURE_FIELDS = {
    "0-1 cm": "soil_moisture_0_to_1cm",
    "1-3 cm": "soil_moisture_1_to_3cm",
    "3-9 cm": "soil_moisture_3_to_9cm",
    "9-27 cm": "soil_moisture_9_to_27cm",
    "27-81 cm": "soil_moisture_27_to_81cm",
}
SOIL_TEMPERATURE_FIELDS = {
    "surface": "soil_temperature_0cm",
    "6 cm": "soil_temperature_6cm",
    "18 cm": "soil_temperature_18cm",
    "54 cm": "soil_temperature_54cm",
}


def _records(block: dict[str, Any], time_key: str, output_time_key: str) -> list[dict[str, Any]]:
    times = block.get(time_key)
    if not isinstance(times, list):
        raise ProviderCollectionError(f"Open-Meteo response omitted {time_key}")
    values = {key: value for key, value in block.items() if key != time_key}
    for key, sequence in values.items():
        if not isinstance(sequence, list) or len(sequence) != len(times):
            raise ProviderCollectionError(
                f"Open-Meteo field {key} does not align with {time_key}"
            )
    return [
        {
            output_time_key: timestamp,
            **{key: values[key][index] for key in values},
        }
        for index, timestamp in enumerate(times)
    ]


def _sum(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in records if row.get(field) is not None]
    return round(sum(values), 2) if values else None


def _min(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in records if row.get(field) is not None]
    return round(min(values), 2) if values else None


def _max(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in records if row.get(field) is not None]
    return round(max(values), 2) if values else None


def _null_counts(records: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, int]:
    return {
        field: sum(row.get(field) is None for row in records)
        for field in fields
    }


def fetch_open_meteo(
    location: LocationTarget,
    *,
    output_path: Path | None = None,
    past_days: int = 7,
    forecast_days: int = 7,
    session: requests.Session | None = None,
    timeout: float = 90.0,
    max_age_hours: float = 1.0,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> FetchOutcome:
    """Fetch the operational weather contract required by CropSage scoring."""
    if not 1 <= past_days <= 92:
        raise ValueError("past_days must be between 1 and 92")
    if not 1 <= forecast_days <= 16:
        raise ValueError("forecast_days must be between 1 and 16")
    output = output_path or default_provider_directory(location) / "open_meteo.json"
    reference = (now or utc_now()).astimezone(timezone.utc)
    cached = cached_artifact(
        output,
        max_age_hours=max_age_hours,
        now=reference,
        force_refresh=force_refresh,
    )
    if cached is not None:
        return FetchOutcome("open_meteo", cached, output, "fresh_cache")

    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": ",".join(CURRENT_VARIABLES),
        "hourly": ",".join(HOURLY_VARIABLES),
        "daily": ",".join(DAILY_VARIABLES),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }
    http = session or requests.Session()
    response = http.get(FORECAST_URL, params=params, timeout=timeout)
    payload = safe_response_json(response, "Open-Meteo")
    current = payload.get("current")
    daily = payload.get("daily")
    hourly = payload.get("hourly")
    if not all(isinstance(block, dict) for block in (current, daily, hourly)):
        raise ProviderCollectionError("Open-Meteo response omitted current, daily, or hourly data")

    daily_records = _records(daily, "time", "date")
    hourly_records = _records(hourly, "time", "local_time")
    try:
        current_date = date.fromisoformat(str(current["time"])[:10])
    except (KeyError, ValueError) as exc:
        raise ProviderCollectionError("Open-Meteo current time is invalid") from exc
    recent_records = [
        row for row in daily_records if date.fromisoformat(str(row["date"])[:10]) < current_date
    ][-past_days:]
    forecast_records = [
        row for row in daily_records if date.fromisoformat(str(row["date"])[:10]) >= current_date
    ][:forecast_days]
    if len(recent_records) < past_days or len(forecast_records) < forecast_days:
        raise ProviderCollectionError(
            "Open-Meteo returned fewer complete recent or forecast days than requested"
        )
    for row in forecast_records:
        precipitation = row.get("precipitation_sum")
        et0 = row.get("et0_fao_evapotranspiration")
        row["RAIN_MINUS_ET0_MM"] = (
            None if precipitation is None or et0 is None else round(float(precipitation) - float(et0), 3)
        )

    current_units = payload.get("current_units", {})
    moisture_profile = [
        {
            "depth": depth,
            "soil_moisture": current.get(field),
            "units": current_units.get(field),
        }
        for depth, field in SOIL_MOISTURE_FIELDS.items()
    ]
    temperature_profile = [
        {
            "depth": depth,
            "soil_temperature": current.get(field),
            "units": current_units.get(field),
        }
        for depth, field in SOIL_TEMPERATURE_FIELDS.items()
    ]
    current_missing = [
        field for field in CURRENT_VARIABLES if field not in current or current.get(field) is None
    ]
    operational_summary = {
        "recent_7_day_rainfall_mm": _sum(recent_records, "precipitation_sum"),
        "forecast_7_day_rainfall_mm": _sum(forecast_records, "precipitation_sum"),
        "forecast_7_day_et0_mm": _sum(forecast_records, "et0_fao_evapotranspiration"),
        "forecast_rain_minus_et0_mm": _sum(forecast_records, "RAIN_MINUS_ET0_MM"),
        "forecast_wet_days": float(
            sum(float(row.get("precipitation_sum") or 0) >= 1.0 for row in forecast_records)
        ),
        "forecast_heat_days_at_or_above_35c": float(
            sum(
                row.get("temperature_2m_max") is not None
                and float(row["temperature_2m_max"]) >= 35.0
                for row in forecast_records
            )
        ),
        "forecast_frost_risk_days_at_or_below_0c": float(
            sum(
                row.get("temperature_2m_min") is not None
                and float(row["temperature_2m_min"]) <= 0.0
                for row in forecast_records
            )
        ),
        "forecast_min_temperature_c": _min(forecast_records, "temperature_2m_min"),
        "forecast_max_temperature_c": _max(forecast_records, "temperature_2m_max"),
    }
    artifact = {
        "schema_version": "1.0",
        "provider": "Open-Meteo",
        "status": "validated",
        "generated_at": reference.isoformat(),
        "farm": {
            **location.provider_farm(),
            "crop_region": location.texas_region_id,
        },
        "interpretation": {
            "evidence_role": "recent_and_forecast_weather",
            "spatial_warning": "Modeled weather-grid evidence; not an on-farm sensor measurement.",
            "soil_warning": "Modeled soil moisture and temperature; permanent soil properties come from SSURGO or a soil test.",
            "water_warning": "Rain minus ET0 is a screening indicator, not an irrigation prescription.",
        },
        "request_trace": {
            "forecast_url": str(getattr(response, "url", FORECAST_URL)),
        },
        "geocoding": {
            "query": None,
            "selected_result": None,
            "limitation": "No geocoder was called; the supplied farm coordinate is authoritative.",
        },
        "provider_grid": {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation_m": payload.get("elevation"),
            "timezone": payload.get("timezone"),
            "timezone_abbreviation": payload.get("timezone_abbreviation"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
        },
        "units": {
            "current": current_units,
            "hourly": payload.get("hourly_units", {}),
            "daily": payload.get("daily_units", {}),
        },
        "current": {
            "model_time": current.get("time"),
            "values": current,
            "soil_moisture_profile": moisture_profile,
            "soil_temperature_profile": temperature_profile,
        },
        "recent_complete_days": {
            "requested_days": past_days,
            "records": recent_records,
        },
        "forecast": {
            "requested_days": forecast_days,
            "daily_records": forecast_records,
            "hourly_records": hourly_records,
            "operational_summary": operational_summary,
        },
        "quality": {
            "current_missing_fields": current_missing,
            "daily_null_counts": _null_counts(daily_records, DAILY_VARIABLES),
            "hourly_null_counts": _null_counts(hourly_records, HOURLY_VARIABLES),
            "recent_day_count": len(recent_records),
            "forecast_day_count": len(forecast_records),
            "hourly_record_count": len(hourly_records),
        },
    }
    write_json_atomic(output, artifact)
    return FetchOutcome("open_meteo", artifact, output, "live")
