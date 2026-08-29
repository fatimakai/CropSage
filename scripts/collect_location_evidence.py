"""Collect four provider artifacts for a Texas location and build its EvidenceBundle."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from providers import (
    FetchOutcome,
    LocationTarget,
    fetch_fortyguard,
    fetch_nasa_power,
    fetch_open_meteo,
    fetch_ssurgo,
)
from providers.common import (
    ROOT,
    default_provider_directory,
    load_simple_env,
    manifest_target,
)
from scripts.build_location_evidence import build_bundle_from_paths, write_bundle


ProviderCall = Callable[[], FetchOutcome]


@dataclass(frozen=True)
class CollectionResult:
    location: LocationTarget
    providers: dict[str, FetchOutcome]
    bundle_path: Path | None


def collect_location(
    location: LocationTarget,
    *,
    output_directory: Path | None = None,
    heat_end_date: date | None = None,
    history_year: int | None = None,
    force_refresh: bool = False,
    build_bundle: bool = True,
    parallel: bool = True,
    provider_functions: dict[str, Callable[..., FetchOutcome]] | None = None,
) -> CollectionResult:
    """Run all provider adapters, preserving successful caches if one fails."""
    provider_dir = output_directory or default_provider_directory(location)
    provider_dir.mkdir(parents=True, exist_ok=True)
    functions = provider_functions or {
        "nasa_power": fetch_nasa_power,
        "open_meteo": fetch_open_meteo,
        "ssurgo": fetch_ssurgo,
        "fortyguard": fetch_fortyguard,
    }
    calls: dict[str, ProviderCall] = {
        "nasa_power": lambda: functions["nasa_power"](
            location,
            output_path=provider_dir / "nasa_power.json",
            history_year=history_year,
            force_refresh=force_refresh,
        ),
        "open_meteo": lambda: functions["open_meteo"](
            location,
            output_path=provider_dir / "open_meteo.json",
            force_refresh=force_refresh,
        ),
        "ssurgo": lambda: functions["ssurgo"](
            location,
            output_path=provider_dir / "ssurgo.json",
            force_refresh=force_refresh,
        ),
        "fortyguard": lambda: functions["fortyguard"](
            location,
            output_path=provider_dir / "fortyguard.json",
            end_date=heat_end_date,
            force_refresh=force_refresh,
        ),
    }
    outcomes: dict[str, FetchOutcome] = {}
    failures: dict[str, Exception] = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(call): name for name, call in calls.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    outcomes[name] = future.result()
                except Exception as exc:  # preserve all provider names for one useful error
                    failures[name] = exc
    else:
        for name, call in calls.items():
            try:
                outcomes[name] = call()
            except Exception as exc:
                failures[name] = exc
    if failures:
        details = "; ".join(f"{name}: {error}" for name, error in failures.items())
        raise RuntimeError(
            f"Provider collection failed ({details}). Successful provider caches were kept."
        )

    bundle_path = None
    if build_bundle:
        provider_paths = {
            name: outcomes[name].output_path
            for name in ("nasa_power", "open_meteo", "ssurgo", "fortyguard")
        }
        bundle = build_bundle_from_paths(location.bundle_target(), provider_paths)
        bundle_path = provider_dir / "evidence_bundle.json"
        write_bundle(bundle, bundle_path)
    return CollectionResult(location, outcomes, bundle_path)


def _location_from_args(args: argparse.Namespace) -> LocationTarget:
    if args.site_id:
        return manifest_target(args.site_id)
    required = {
        "farm_id": args.farm_id,
        "farm_name": args.farm_name,
        "latitude": args.latitude,
        "longitude": args.longitude,
        "region_id": args.region_id,
        "timezone": args.timezone,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(
            "Use --site-id or supply every custom-location field. Missing: "
            + ", ".join(missing)
        )
    return LocationTarget(
        farm_id=args.farm_id,
        farm_name=args.farm_name,
        latitude=float(args.latitude),
        longitude=float(args.longitude),
        texas_region_id=args.region_id,
        timezone=args.timezone,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    location = parser.add_mutually_exclusive_group(required=False)
    location.add_argument("--site-id", help="Site ID from texas_region_sites.json")
    location.add_argument("--farm-id", help="Stable ID for a custom Texas farm")
    parser.add_argument("--farm-name")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--region-id")
    parser.add_argument("--timezone")
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--heat-end-date", type=date.fromisoformat)
    parser.add_argument("--history-year", type=int)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--skip-bundle", action="store_true")
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="KEY=VALUE file containing FORTYGUARD_API_KEY (default: project .env)",
    )
    args = parser.parse_args()
    load_simple_env(args.env_file)
    target = _location_from_args(args)
    result = collect_location(
        target,
        output_directory=args.output_directory,
        heat_end_date=args.heat_end_date,
        history_year=args.history_year,
        force_refresh=args.force_refresh,
        build_bundle=not args.skip_bundle,
        parallel=not args.sequential,
    )
    print(f"Collected evidence for: {result.location.farm_name}")
    for provider in ("nasa_power", "open_meteo", "ssurgo", "fortyguard"):
        outcome = result.providers[provider]
        print(f"- {provider}: {outcome.cache_state} -> {outcome.output_path}")
    if result.bundle_path:
        print(f"Validated EvidenceBundle -> {result.bundle_path}")


if __name__ == "__main__":
    main()
