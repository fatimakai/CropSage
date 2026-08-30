"""Score and validate the complete 15-site, 75-profile scenario matrix."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scoring.score_crops import score_crops
from scoring.validate_recommendations import validate_ranking_contract


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "data" / "scenarios"
SCENARIO_MANIFEST_PATH = SCENARIO_ROOT / "scenario_manifest.json"
RESULTS_ROOT = SCENARIO_ROOT / "results"
AGGREGATE_RESULTS_PATH = SCENARIO_ROOT / "scenario_results.json"
SUMMARY_CSV_PATH = SCENARIO_ROOT / "scenario_summary.csv"
VALIDATION_REPORT_PATH = SCENARIO_ROOT / "scenario_validation_report.json"
CONFIG_PATH = ROOT / "data" / "scoring" / "crop_scoring_config.json"
RECOMMENDATION_SCHEMA_PATH = ROOT / "data" / "scoring" / "recommendation.schema.json"
EXPECTED_RUN_COUNT = 75
EXPECTED_CROPS_PER_RUN = 22
EXPECTED_CROP_RESULT_COUNT = EXPECTED_RUN_COUNT * EXPECTED_CROPS_PER_RUN
SUMMARY_FIELDS = (
    "site_id",
    "parent_region_id",
    "scenario_type",
    "profile_id",
    "evidence_bundle_id",
    "evaluation_mode",
    "requested_crop_id",
    "is_requested_crop",
    "crop_id",
    "crop_name",
    "regionally_eligible",
    "overall_rank",
    "eligible_rank",
    "suitability_score",
    "recommendation",
    "confidence_score",
    "confidence_band",
    "evidence_coverage_percent",
    "applied_caps",
    "applied_gates",
    "detailed_output_path",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def document_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def invalid_numeric_count(value: Any) -> int:
    if isinstance(value, float):
        return 0 if math.isfinite(value) else 1
    if isinstance(value, dict):
        return sum(invalid_numeric_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(invalid_numeric_count(item) for item in value)
    return 0


def factor_by_id(crop_result: dict[str, Any], factor_id: str) -> dict[str, Any]:
    return next(item for item in crop_result["factors"] if item["factor_id"] == factor_id)


def gate_names(crop_result: dict[str, Any], field: str) -> list[str]:
    return [item["gate"] for item in crop_result[field]]


def validate_scenario_behavior(
    scenario_type: str, output: dict[str, Any]
) -> dict[str, bool]:
    requested = output["requested_crop_result"]
    if requested is None:
        raise ValueError(f"Scenario profile has no requested crop: {output['profile_id']}")
    planting = factor_by_id(requested, "planting_window")
    checks = {
        "requested_crop_result_matches_ranking": requested
        == next(item for item in output["rankings"] if item["crop_id"] == output["requested_crop_id"]),
        "expected_evaluation_mode": output["evaluation_mode"]
        == ("planning" if scenario_type == "out_of_season" else "planting_readiness"),
    }
    if scenario_type == "out_of_season":
        checks.update(
            {
                "requested_crop_outside_planting_window": planting["score"] == 0,
                "requested_crop_has_planting_gate": "far_outside_planting_window"
                in gate_names(requested, "applied_gates"),
                "requested_crop_respects_planting_cap": requested["suitability_score"] is not None
                and requested["suitability_score"] <= 54,
            }
        )
    else:
        checks["requested_crop_inside_planting_window"] = planting["score"] == 100

    if scenario_type == "no_irrigation":
        checks["no_irrigation_factor_is_scored"] = all(
            factor_by_id(item, "irrigation_availability")["available"]
            for item in output["rankings"]
        )
    elif scenario_type == "reliable_irrigation":
        checks["reliable_irrigation_scores_100"] = all(
            factor_by_id(item, "irrigation_availability")["score"] == 100
            for item in output["rankings"]
        )
    elif scenario_type == "missing_irrigation_lab_ph_override":
        checks.update(
            {
                "missing_irrigation_is_excluded_not_zero": all(
                    not factor_by_id(item, "irrigation_availability")["available"]
                    and factor_by_id(item, "irrigation_availability")["score"] is None
                    for item in output["rankings"]
                ),
                "laboratory_ph_override_is_used": all(
                    factor_by_id(item, "soil_ph")["evidence"]["sources"][0]
                    == "laboratory_measurement"
                    and factor_by_id(item, "soil_ph")["evidence"]["values"]["ph"] == 6.5
                    for item in output["rankings"]
                ),
            }
        )
    return checks


def compact_row(
    site_id: str,
    parent_region_id: str,
    scenario_type: str,
    output: dict[str, Any],
    crop: dict[str, Any],
    detailed_output_path: str,
) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "parent_region_id": parent_region_id,
        "scenario_type": scenario_type,
        "profile_id": output["profile_id"],
        "evidence_bundle_id": output["evidence_bundle_id"],
        "evaluation_mode": output["evaluation_mode"],
        "requested_crop_id": output["requested_crop_id"],
        "is_requested_crop": crop["crop_id"] == output["requested_crop_id"],
        "crop_id": crop["crop_id"],
        "crop_name": crop["crop_name"],
        "regionally_eligible": crop["regionally_eligible"],
        "overall_rank": crop["overall_rank"],
        "eligible_rank": crop["eligible_rank"],
        "suitability_score": crop["suitability_score"],
        "recommendation": crop["recommendation"],
        "confidence_score": crop["confidence_score"],
        "confidence_band": crop["confidence_band"],
        "evidence_coverage_percent": crop["evidence_coverage_percent"],
        "applied_caps": gate_names(crop, "applied_caps"),
        "applied_gates": gate_names(crop, "applied_gates"),
        "detailed_output_path": detailed_output_path,
    }


def write_summary_csv(rows: list[dict[str, Any]]) -> None:
    SUMMARY_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["applied_caps"] = "|".join(row["applied_caps"])
            csv_row["applied_gates"] = "|".join(row["applied_gates"])
            writer.writerow(csv_row)


def run_matrix() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_json(SCENARIO_MANIFEST_PATH)
    config = load_json(CONFIG_PATH)
    schema = load_json(RECOMMENDATION_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    schema_validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rows: list[dict[str, Any]] = []
    run_reports: list[dict[str, Any]] = []
    expected_output_paths: set[Path] = set()

    for site in manifest["sites"]:
        site_id = site["site_id"]
        evidence = load_json(ROOT / site["evidence_bundle_path"])
        for scenario in site["scenarios"]:
            scenario_type = scenario["scenario_type"]
            profile = load_json(ROOT / scenario["profile_path"])
            output = score_crops(evidence, profile, config)
            schema_errors = sorted(
                schema_validator.iter_errors(output),
                key=lambda error: list(error.absolute_path),
            )
            ranking = validate_ranking_contract(output)
            behavior = validate_scenario_behavior(scenario_type, output)
            result_relative = Path("results") / site_id / f"{scenario_type}.json"
            result_path = SCENARIO_ROOT / result_relative
            expected_output_paths.add(result_path)
            run_passed = (
                not schema_errors
                and ranking["eligibility_ranking_policy_passed"]
                and all(behavior.values())
                and invalid_numeric_count(output) == 0
            )
            if not run_passed:
                raise ValueError(
                    f"Scenario validation failed for {profile['profile_id']}: "
                    f"schema={[error.message for error in schema_errors]}, "
                    f"ranking={ranking}, behavior={behavior}"
                )
            save_json(result_path, output)
            detailed_output_path = f"data/scenarios/{result_relative.as_posix()}"
            rows.extend(
                compact_row(
                    site_id,
                    site["parent_region_id"],
                    scenario_type,
                    output,
                    crop,
                    detailed_output_path,
                )
                for crop in output["rankings"]
            )
            run_reports.append(
                {
                    "site_id": site_id,
                    "parent_region_id": site["parent_region_id"],
                    "scenario_type": scenario_type,
                    "profile_id": output["profile_id"],
                    "evidence_bundle_id": output["evidence_bundle_id"],
                    "evaluation_mode": output["evaluation_mode"],
                    "requested_crop_id": output["requested_crop_id"],
                    "output_path": detailed_output_path,
                    "output_sha256": document_hash(output),
                    "schema_valid": not schema_errors,
                    "ranking_policy_valid": ranking["eligibility_ranking_policy_passed"],
                    "behavior_checks": behavior,
                    "crop_result_count": len(output["rankings"]),
                    "eligible_crop_count": ranking["eligible_crop_count"],
                    "ineligible_crop_count": ranking["ineligible_crop_count"],
                    "passed": run_passed,
                }
            )

    existing_paths = set(RESULTS_ROOT.glob("*/*.json")) if RESULTS_ROOT.exists() else set()
    unexpected_paths = existing_paths - expected_output_paths
    if unexpected_paths:
        paths = ", ".join(str(path) for path in sorted(unexpected_paths))
        raise ValueError(f"Refusing to leave stale scenario outputs: {paths}")

    result_keys = {
        (row["site_id"], row["scenario_type"], row["crop_id"]) for row in rows
    }
    global_checks = {
        "run_count_is_75": len(run_reports) == EXPECTED_RUN_COUNT,
        "crop_result_count_is_1650": len(rows) == EXPECTED_CROP_RESULT_COUNT,
        "crop_result_keys_are_unique": len(result_keys) == EXPECTED_CROP_RESULT_COUNT,
        "all_runs_passed": all(run["passed"] for run in run_reports),
        "all_scores_are_valid": all(
            row["suitability_score"] is not None
            and 0 <= row["suitability_score"] <= 100
            and 0 <= row["confidence_score"] <= 100
            for row in rows
        ),
        "all_ineligible_results_are_not_recommended": all(
            row["regionally_eligible"]
            or (
                row["eligible_rank"] is None
                and row["recommendation"] == "not_recommended"
                and row["suitability_score"] <= 54
                and "unsupported_region" in row["applied_gates"]
            )
            for row in rows
        ),
    }
    if not all(global_checks.values()):
        raise ValueError(f"Global scenario validation failed: {global_checks}")

    aggregate = {
        "schema_version": "1.0.0",
        "scenario_manifest_id": manifest["manifest_id"],
        "generated_at": manifest["generated_at"],
        "scoring_version": config["scoring_version"],
        "run_count": len(run_reports),
        "crop_result_count": len(rows),
        "results": rows,
    }
    validation_report = {
        "report_version": "1.0.0",
        "scenario_manifest_id": manifest["manifest_id"],
        "generated_at": manifest["generated_at"],
        "scoring_version": config["scoring_version"],
        "status": "validated",
        "expected_run_count": EXPECTED_RUN_COUNT,
        "actual_run_count": len(run_reports),
        "expected_crop_result_count": EXPECTED_CROP_RESULT_COUNT,
        "actual_crop_result_count": len(rows),
        "global_checks": global_checks,
        "runs": run_reports,
    }
    return aggregate, validation_report


def main() -> None:
    aggregate, validation_report = run_matrix()
    save_json(AGGREGATE_RESULTS_PATH, aggregate)
    write_summary_csv(aggregate["results"])
    save_json(VALIDATION_REPORT_PATH, validation_report)
    print(
        f"Validated {aggregate['run_count']} runs and "
        f"{aggregate['crop_result_count']} crop results"
    )
    print(f"Saved aggregate results: {AGGREGATE_RESULTS_PATH}")
    print(f"Saved CSV summary: {SUMMARY_CSV_PATH}")
    print(f"Saved validation report: {VALIDATION_REPORT_PATH}")


if __name__ == "__main__":
    main()
