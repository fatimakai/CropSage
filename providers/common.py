"""Shared location, cache, JSON, and HTTP utilities for provider adapters."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEXAS_BOUNDS = {
    "latitude_min": 25.8,
    "latitude_max": 36.5,
    "longitude_min": -106.65,
    "longitude_max": -93.5,
}
TEXAS_REGIONS = {
    "plains",
    "eastern",
    "central_south_winter_garden",
    "lower_rio_grande_valley",
    "far_west",
}
TEXAS_TIMEZONES = {"America/Chicago", "America/Denver"}


class ProviderCollectionError(RuntimeError):
    """Raised when a provider cannot produce a valid normalized artifact."""


@dataclass(frozen=True)
class LocationTarget:
    farm_id: str
    farm_name: str
    latitude: float
    longitude: float
    texas_region_id: str
    timezone: str
    representative_site_id: str | None = None

    def __post_init__(self) -> None:
        if not self.farm_id or not self.farm_name:
            raise ValueError("farm_id and farm_name are required")
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude):
            raise ValueError("Location coordinates must be finite")
        if not (
            TEXAS_BOUNDS["latitude_min"]
            <= self.latitude
            <= TEXAS_BOUNDS["latitude_max"]
            and TEXAS_BOUNDS["longitude_min"]
            <= self.longitude
            <= TEXAS_BOUNDS["longitude_max"]
        ):
            raise ValueError("Location must be within the configured Texas bounds")
        if self.texas_region_id not in TEXAS_REGIONS:
            raise ValueError(f"Unsupported Texas region: {self.texas_region_id}")
        if self.timezone not in TEXAS_TIMEZONES:
            raise ValueError(f"Unsupported Texas timezone: {self.timezone}")

    def bundle_target(self) -> dict[str, Any]:
        return {
            "farm_id": self.farm_id,
            "farm_name": self.farm_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "texas_region_id": self.texas_region_id,
            "timezone": self.timezone,
        }

    def provider_farm(self, *, include_timezone: bool = True) -> dict[str, Any]:
        value = {
            "farm_id": self.farm_id,
            "farm_name": self.farm_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        if include_timezone:
            value["timezone"] = self.timezone
        return value


@dataclass(frozen=True)
class FetchOutcome:
    provider: str
    artifact: dict[str, Any]
    output_path: Path
    cache_state: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must contain a UTC offset: {value}")
    return parsed.astimezone(timezone.utc)


def artifact_generated_at(artifact: dict[str, Any]) -> str:
    value = artifact.get("generated_at") or artifact.get("generated_at_utc")
    if not isinstance(value, str):
        raise ValueError("Cached artifact has no generated timestamp")
    return value


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def cached_artifact(
    path: Path,
    *,
    max_age_hours: float,
    now: datetime | None = None,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    if force_refresh or not path.exists():
        return None
    artifact = load_json(path)
    reference = (now or utc_now()).astimezone(timezone.utc)
    age = (reference - parse_datetime(artifact_generated_at(artifact))).total_seconds() / 3600
    if age < -0.25:
        raise ValueError(f"Cached artifact has a future timestamp: {path}")
    return artifact if age <= max_age_hours else None


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_simple_env(path: Path) -> None:
    """Load KEY=VALUE pairs without printing or replacing existing values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def safe_response_json(response: Any, provider: str) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise ProviderCollectionError(
            f"{provider} returned a non-JSON response with HTTP {response.status_code}"
        ) from exc
    if not response.ok:
        message = value.get("reason") or value.get("message") or value.get("header")
        raise ProviderCollectionError(
            f"{provider} request failed with HTTP {response.status_code}: {message or 'unknown error'}"
        )
    if not isinstance(value, dict):
        raise ProviderCollectionError(f"{provider} returned a non-object JSON response")
    return value


def manifest_target(site_id: str, manifest_path: Path | None = None) -> LocationTarget:
    path = manifest_path or ROOT / "data" / "regions" / "texas_region_sites.json"
    manifest = load_json(path)
    site = next((row for row in manifest["sites"] if row["site_id"] == site_id), None)
    if site is None:
        raise ValueError(f"Unknown representative site: {site_id}")
    return LocationTarget(
        farm_id=site["site_id"],
        farm_name=site["name"],
        latitude=float(site["location"]["latitude"]),
        longitude=float(site["location"]["longitude"]),
        texas_region_id=site["parent_region_id"],
        timezone=site["timezone"],
        representative_site_id=site["site_id"],
    )


def default_provider_directory(location: LocationTarget) -> Path:
    key = location.representative_site_id or location.farm_id
    return ROOT / "data" / "evidence" / "regions" / key
