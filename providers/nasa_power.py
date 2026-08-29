"""NASA POWER collector producing the tested CropSage provider artifact."""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

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


CLIMATOLOGY_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
COMMUNITY = "AG"
PRIMARY_PARAMETERS = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "ALLSKY_SFC_SW_DWN",
)
ADDITIONAL_PARAMETERS = (
    "WS2M",
    "T2MDEW",
    "ALLSKY_SFC_PAR_TOT",
    "GWETROOT",
    "EVPTRNS",
)
ALL_PARAMETERS = PRIMARY_PARAMETERS + ADDITIONAL_PARAMETERS
MISSING_SENTINELS = {-999.0, -9999.0}


def _clean_number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number in MISSING_SENTINELS or not math.isfinite(number):
        return None
    return number


def _request(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], str]:
    response = session.get(url, params=params, timeout=timeout)
    payload = safe_response_json(response, "NASA POWER")
    return payload, str(getattr(response, "url", url))


def _parameter_values(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        values = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise ProviderCollectionError("NASA POWER response omitted properties.parameter") from exc
    if not isinstance(values, dict):
        raise ProviderCollectionError("NASA POWER parameter payload is not an object")
    return values


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return fmean(valid) if valid else None


def _sum(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return sum(valid) if valid else None


def _maximum(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return max(valid) if valid else None


def _minimum(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return min(valid) if valid else None


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _vpd_kpa(temperature_c: float | None, dew_point_c: float | None) -> float | None:
    if temperature_c is None or dew_point_c is None:
        return None
    saturation = 0.6108 * math.exp((17.27 * temperature_c) / (temperature_c + 237.3))
    actual = 0.6108 * math.exp((17.27 * dew_point_c) / (dew_point_c + 237.3))
    return max(0.0, saturation - actual)


def _daily_records(
    values: dict[str, dict[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    returned = set(values)
    missing_parameters = sorted(set(ALL_PARAMETERS) - returned)
    date_keys = sorted({key for mapping in values.values() for key in mapping})
    expected = {
        current.strftime("%Y%m%d")
        for ordinal in range(start_date.toordinal(), end_date.toordinal() + 1)
        for current in [date.fromordinal(ordinal)]
    }
    missing_dates = sorted(expected - set(date_keys))
    records: list[dict[str, Any]] = []
    missing_report = []
    for parameter in ALL_PARAMETERS:
        mapping = values.get(parameter, {})
        raw_values = list(mapping.values())
        missing_report.append(
            {
                "parameter": parameter,
                "sentinel_count": sum(
                    value is not None and float(value) in MISSING_SENTINELS
                    for value in raw_values
                ),
                "null_count": sum(_clean_number(value) is None for value in raw_values),
            }
        )
    for key in date_keys:
        parsed = datetime.strptime(key, "%Y%m%d").date()
        if parsed < start_date or parsed > end_date:
            continue
        record: dict[str, Any] = {"date": parsed.isoformat()}
        for parameter in ALL_PARAMETERS:
            record[parameter] = _clean_number(values.get(parameter, {}).get(key))
        record["VPD_KPA"] = _round(_vpd_kpa(record["T2M"], record["T2MDEW"]))
        if record["T2M_MAX"] is not None and record["T2M_MIN"] is not None:
            record["TEMPERATURE_RANGE_C"] = _round(record["T2M_MAX"] - record["T2M_MIN"])
            mean_for_gdd = (record["T2M_MAX"] + record["T2M_MIN"]) / 2
            record["GDD_BASE_10"] = _round(max(0.0, mean_for_gdd - 10.0))
            record["HEAT_STRESS_DAY_35C"] = int(record["T2M_MAX"] >= 35.0)
        else:
            record["TEMPERATURE_RANGE_C"] = None
            record["GDD_BASE_10"] = None
            record["HEAT_STRESS_DAY_35C"] = None
        records.append(record)
    return records, missing_parameters + missing_dates, missing_report


def _monthly_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[date.fromisoformat(record["date"]).month].append(record)
    rows = []
    for month in range(1, 13):
        values = grouped.get(month, [])
        rows.append(
            {
                "month": calendar.month_abbr[month],
                "T2M": _round(_mean(row["T2M"] for row in values)),
                "T2M_MAX": _round(_maximum(row["T2M_MAX"] for row in values)),
                "T2M_MIN": _round(_minimum(row["T2M_MIN"] for row in values)),
                "PRECIPITATION_TOTAL_MM": _round(_sum(row["PRECTOTCORR"] for row in values)),
                "RH2M": _round(_mean(row["RH2M"] for row in values)),
                "ALLSKY_SFC_SW_DWN": _round(_mean(row["ALLSKY_SFC_SW_DWN"] for row in values)),
                "WS2M": _round(_mean(row["WS2M"] for row in values)),
                "T2MDEW": _round(_mean(row["T2MDEW"] for row in values)),
                "ALLSKY_SFC_PAR_TOT": _round(_mean(row["ALLSKY_SFC_PAR_TOT"] for row in values)),
                "GWETROOT": _round(_mean(row["GWETROOT"] for row in values)),
                "EVPTRNS_TOTAL_MJ_M2": _round(_sum(row["EVPTRNS"] for row in values)),
                "VPD_KPA": _round(_mean(row["VPD_KPA"] for row in values)),
                "GDD_BASE_10": _round(_sum(row["GDD_BASE_10"] for row in values)),
                "HEAT_STRESS_DAY_35C": int(_sum(row["HEAT_STRESS_DAY_35C"] for row in values) or 0),
            }
        )
    return rows


def _annual_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mean_temperature_c": _round(_mean(row["T2M"] for row in records), 2),
        "highest_temperature_c": _round(_maximum(row["T2M_MAX"] for row in records), 2),
        "lowest_temperature_c": _round(_minimum(row["T2M_MIN"] for row in records), 2),
        "annual_precipitation_mm": _round(_sum(row["PRECTOTCORR"] for row in records), 2),
        "mean_relative_humidity_percent": _round(_mean(row["RH2M"] for row in records), 2),
        "mean_wind_speed_m_s": _round(_mean(row["WS2M"] for row in records), 2),
        "mean_solar_radiation_mj_m2_day": _round(_mean(row["ALLSKY_SFC_SW_DWN"] for row in records), 2),
        "mean_par_mj_m2_day": _round(_mean(row["ALLSKY_SFC_PAR_TOT"] for row in records), 2),
        "mean_root_zone_wetness": _round(_mean(row["GWETROOT"] for row in records), 2),
        "mean_vpd_kpa": _round(_mean(row["VPD_KPA"] for row in records), 2),
        "gdd_base_10": _round(_sum(row["GDD_BASE_10"] for row in records), 2),
        "heat_stress_days_above_35c": float(
            _sum(row["HEAT_STRESS_DAY_35C"] for row in records) or 0
        ),
    }


def fetch_nasa_power(
    location: LocationTarget,
    *,
    output_path: Path | None = None,
    history_year: int | None = None,
    session: requests.Session | None = None,
    timeout: float = 90.0,
    max_age_hours: float = 720.0,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> FetchOutcome:
    """Fetch climatology and the latest complete calendar year for one location."""
    output = output_path or default_provider_directory(location) / "nasa_power.json"
    reference = (now or utc_now()).astimezone(timezone.utc)
    cached = cached_artifact(
        output,
        max_age_hours=max_age_hours,
        now=reference,
        force_refresh=force_refresh,
    )
    if cached is not None:
        return FetchOutcome("nasa_power", cached, output, "fresh_cache")

    year = history_year or (reference.year - 1)
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    http = session or requests.Session()
    base_params = {
        "community": COMMUNITY,
        "longitude": location.longitude,
        "latitude": location.latitude,
        "format": "JSON",
    }
    primary, primary_url = _request(
        http,
        CLIMATOLOGY_URL,
        {**base_params, "parameters": ",".join(PRIMARY_PARAMETERS)},
        timeout,
    )
    additional, additional_url = _request(
        http,
        CLIMATOLOGY_URL,
        {**base_params, "parameters": ",".join(ADDITIONAL_PARAMETERS)},
        timeout,
    )
    daily, daily_url = _request(
        http,
        DAILY_URL,
        {
            **base_params,
            "parameters": ",".join(ALL_PARAMETERS),
            "start": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "time-standard": "LST",
        },
        timeout,
    )
    climatology_values = {
        **_parameter_values(primary),
        **_parameter_values(additional),
    }
    periods = [
        "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "ANN",
    ]
    climatology_rows = []
    for period in periods:
        if not any(period in mapping for mapping in climatology_values.values()):
            continue
        row: dict[str, Any] = {"period": period}
        for parameter in ALL_PARAMETERS:
            row[parameter] = _clean_number(climatology_values.get(parameter, {}).get(period))
        climatology_rows.append(row)

    daily_values = _parameter_values(daily)
    records, missing_items, missing_report = _daily_records(
        daily_values, start_date, end_date
    )
    missing_parameters = sorted(set(ALL_PARAMETERS) - set(daily_values))
    expected_dates = {
        date.fromordinal(ordinal).isoformat()
        for ordinal in range(start_date.toordinal(), end_date.toordinal() + 1)
    }
    returned_dates = {row["date"] for row in records}
    missing_dates = sorted(expected_dates - returned_dates)
    metadata = {
        **primary.get("parameters", {}),
        **additional.get("parameters", {}),
    }
    artifact = {
        "schema_version": "1.0",
        "provider": "NASA POWER",
        "status": "validated",
        "generated_at": reference.isoformat(),
        "farm": location.provider_farm(),
        "interpretation": {
            "evidence_role": "long_term_climate_baseline_and_daily_history",
            "spatial_warning": (
                "NASA POWER is modeled gridded climate evidence, not an on-farm sensor measurement."
            ),
            "time_standard": "Local Solar Time (LST)",
            "climatology_period": "January 2001 - December 2020",
        },
        "request_trace": {
            "climatology_url": primary_url,
            "additional_climatology_url": additional_url,
            f"daily_{year}_url": daily_url,
        },
        "provider_geometry": daily.get("geometry") or primary.get("geometry"),
        "parameter_metadata": metadata,
        "climatology": {"monthly_and_annual": climatology_rows},
        f"daily_history_{year}": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "annual_summary": _annual_summary(records),
            "monthly_summary": _monthly_summary(records),
            "daily_records": records,
        },
        "daily_history_2025": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "annual_summary": _annual_summary(records),
            "monthly_summary": _monthly_summary(records),
            "daily_records": records,
        },
        "quality": {
            "requested_parameter_count": len(ALL_PARAMETERS),
            "returned_parameter_count": len(daily_values),
            "returned_day_count": len(records),
            "missing_parameters": missing_parameters,
            "unexpected_parameters": sorted(set(daily_values) - set(ALL_PARAMETERS)),
            "missing_dates": missing_dates,
            "missing_value_report": missing_report,
            "normalization_warnings": missing_items,
        },
    }
    if year != 2025:
        # The current EvidenceBundle contract retains the historical key name.
        # Its embedded dates remain authoritative until schema 1.2 removes it.
        artifact["interpretation"]["history_key_warning"] = (
            "daily_history_2025 is a compatibility alias; inspect start_date and end_date."
        )
    write_json_atomic(output, artifact)
    return FetchOutcome("nasa_power", artifact, output, "live")
