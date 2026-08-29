"""Collect and validate EvidenceBundles for the 15 representative Texas sites."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from providers.common import ROOT, load_json, load_simple_env, manifest_target, write_json_atomic
from scripts.collect_location_evidence import collect_location


MANIFEST_PATH = ROOT / "data" / "regions" / "texas_region_sites.json"
DEFAULT_SUMMARY_PATH = ROOT / "data" / "evidence" / "regions" / "collection_summary.json"


def collect_all_sites(
    site_ids: list[str],
    *,
    max_workers: int = 2,
    force_refresh: bool = False,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, Any]:
    if not 1 <= max_workers <= 4:
        raise ValueError("max_workers must be between 1 and 4")
    started_at = datetime.now(timezone.utc)
    results: dict[str, Any] = {}

    def run(site_id: str) -> tuple[str, Any]:
        location = manifest_target(site_id)
        outcome = collect_location(location, force_refresh=force_refresh)
        return site_id, outcome

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run, site_id): site_id for site_id in site_ids}
        for future in as_completed(futures):
            site_id = futures[future]
            try:
                _, outcome = future.result()
                results[site_id] = {
                    "status": "validated",
                    "bundle_path": str(outcome.bundle_path),
                    "provider_cache_states": {
                        name: provider.cache_state
                        for name, provider in outcome.providers.items()
                    },
                }
                print(f"VALIDATED {site_id}", flush=True)
            except Exception as exc:
                results[site_id] = {"status": "failed", "error": str(exc)}
                print(f"FAILED {site_id}: {exc}", flush=True)
            write_json_atomic(
                summary_path,
                {
                    "started_at": started_at.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "requested_site_count": len(site_ids),
                    "validated_site_count": sum(
                        row["status"] == "validated" for row in results.values()
                    ),
                    "failed_site_count": sum(
                        row["status"] == "failed" for row in results.values()
                    ),
                    "sites": results,
                },
            )
    summary = load_json(summary_path)
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-id",
        action="append",
        dest="site_ids",
        help="Collect only this site; repeat for multiple sites (default: all 15)",
    )
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    load_simple_env(args.env_file)
    manifest = load_json(MANIFEST_PATH)
    known = [site["site_id"] for site in manifest["sites"]]
    selected = args.site_ids or known
    unknown = sorted(set(selected) - set(known))
    if unknown:
        parser.error(f"Unknown site IDs: {', '.join(unknown)}")
    summary = collect_all_sites(
        selected,
        max_workers=args.max_workers,
        force_refresh=args.force_refresh,
        summary_path=args.summary,
    )
    print(f"Summary: {args.summary}")
    print(
        f"Validated: {summary['validated_site_count']}/{summary['requested_site_count']}; "
        f"failed: {summary['failed_site_count']}"
    )
    if summary["failed_site_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
