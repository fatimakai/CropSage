"""Run conservative ranking and one-factor weight sensitivity checks for v1."""

from __future__ import annotations

import copy
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from scoring.score_crops import score_crops


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "data" / "scenarios"
MANIFEST_PATH = SCENARIO_ROOT / "scenario_manifest.json"
BASELINE_RESULTS_PATH = SCENARIO_ROOT / "scenario_results.json"
CONFIG_PATH = ROOT / "data" / "scoring" / "crop_scoring_config.json"
REPORT_PATH = SCENARIO_ROOT / "scoring_sensitivity_report.json"
WEIGHT_MULTIPLIER = 1.2


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def perturbed_config(config: dict[str, Any], factor_id: str) -> dict[str, Any]:
    result = copy.deepcopy(config)
    weights = result["weights_percent"]
    old_weight = float(weights[factor_id])
    if old_weight <= 0:
        raise ValueError(f"Cannot perturb inactive factor {factor_id}")
    new_weight = old_weight * WEIGHT_MULTIPLIER
    other_active = [key for key, value in weights.items() if key != factor_id and value > 0]
    other_total = sum(float(weights[key]) for key in other_active)
    scale = (100.0 - new_weight) / other_total
    weights[factor_id] = new_weight
    for key in other_active:
        weights[key] = float(weights[key]) * scale
    # Eliminate floating-point residue without changing the intended perturbation.
    residual = 100.0 - sum(float(value) for value in weights.values())
    weights[other_active[-1]] += residual
    return result


def scenario_inputs(manifest: dict[str, Any]) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    inputs = []
    for site in manifest["sites"]:
        evidence = load_json(ROOT / site["evidence_bundle_path"])
        for scenario in site["scenarios"]:
            profile = load_json(ROOT / scenario["profile_path"])
            inputs.append((site["site_id"], scenario["scenario_type"], evidence, profile))
    return inputs


def run_compact(
    inputs: list[tuple[str, str, dict[str, Any], dict[str, Any]]],
    config: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows = {}
    for site_id, scenario_type, evidence, profile in inputs:
        output = score_crops(evidence, profile, config)
        for crop in output["rankings"]:
            rows[(site_id, scenario_type, crop["crop_id"])] = {
                "suitability_score": crop["suitability_score"],
                "recommendation": crop["recommendation"],
                "overall_rank": crop["overall_rank"],
            }
    return rows


def saved_compact(results: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (row["site_id"], row["scenario_type"], row["crop_id"]): {
            "suitability_score": row["suitability_score"],
            "recommendation": row["recommendation"],
            "overall_rank": row["overall_rank"],
        }
        for row in results["results"]
    }


def top_crops(rows: dict[tuple[str, str, str], dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {
        (site_id, scenario_type): crop_id
        for (site_id, scenario_type, crop_id), result in rows.items()
        if result["overall_rank"] == 1
    }


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    config = load_json(CONFIG_PATH)
    baseline_document = load_json(BASELINE_RESULTS_PATH)
    baseline = saved_compact(baseline_document)
    inputs = scenario_inputs(manifest)
    fresh_baseline = run_compact(inputs, config)
    if fresh_baseline != baseline:
        raise ValueError("Saved scenario results do not match the current scoring engine")

    baseline_tops = top_crops(baseline)
    sensitivity = []
    for factor_id, weight in config["weights_percent"].items():
        if weight <= 0:
            continue
        candidate = run_compact(inputs, perturbed_config(config, factor_id))
        score_deltas = [
            abs(candidate[key]["suitability_score"] - baseline[key]["suitability_score"])
            for key in baseline
        ]
        rank_deltas = [
            abs(candidate[key]["overall_rank"] - baseline[key]["overall_rank"])
            for key in baseline
        ]
        candidate_tops = top_crops(candidate)
        sensitivity.append(
            {
                "factor_id": factor_id,
                "baseline_weight_percent": weight,
                "perturbed_weight_percent": round(weight * WEIGHT_MULTIPLIER, 6),
                "mean_absolute_score_change": round(statistics.mean(score_deltas), 4),
                "maximum_absolute_score_change": round(max(score_deltas), 4),
                "recommendation_class_changes": sum(
                    candidate[key]["recommendation"] != baseline[key]["recommendation"]
                    for key in baseline
                ),
                "rank_changes": sum(
                    candidate[key]["overall_rank"] != baseline[key]["overall_rank"]
                    for key in baseline
                ),
                "maximum_absolute_rank_change": max(rank_deltas),
                "top_crop_changes": sum(
                    candidate_tops[key] != baseline_tops[key] for key in baseline_tops
                ),
            }
        )

    rows = baseline_document["results"]
    by_key = {
        (row["site_id"], row["scenario_type"], row["crop_id"]): row for row in rows
    }
    sites = {row["site_id"] for row in rows}
    crops = {row["crop_id"] for row in rows}
    limited_below_none = 0
    reliable_below_limited = 0
    for site_id in sites:
        for crop_id in crops:
            none = by_key[(site_id, "no_irrigation", crop_id)]["suitability_score"]
            limited = by_key[(site_id, "in_season_baseline", crop_id)]["suitability_score"]
            reliable = by_key[(site_id, "reliable_irrigation", crop_id)]["suitability_score"]
            limited_below_none += limited < none
            reliable_below_limited += reliable < limited

    report = {
        "report_version": "1.0.0",
        "scoring_version_reviewed": config["scoring_version"],
        "scenario_manifest_id": manifest["manifest_id"],
        "weight_perturbation": "+20% for one active factor while proportionally rescaling all other active factors to retain a 100% total",
        "run_count_per_weight_test": 75,
        "crop_result_count_per_weight_test": 1650,
        "active_factor_count": len(sensitivity),
        "baseline_summary": {
            "recommendation_counts": dict(Counter(row["recommendation"] for row in rows)),
            "confidence_band_counts": dict(Counter(row["confidence_band"] for row in rows)),
            "gate_counts": dict(
                Counter(gate for row in rows for gate in row["applied_gates"])
            ),
            "top_crop_counts": dict(
                Counter(
                    row["crop_id"] for row in rows if row["overall_rank"] == 1
                )
            ),
        },
        "logical_checks": {
            "limited_irrigation_below_no_irrigation_count": limited_below_none,
            "reliable_irrigation_below_limited_irrigation_count": reliable_below_limited,
            "all_out_of_season_requested_crops_capped": all(
                row["suitability_score"] <= 54
                and "far_outside_planting_window" in row["applied_gates"]
                for row in rows
                if row["scenario_type"] == "out_of_season" and row["is_requested_crop"]
            ),
            "all_ineligible_crops_gated": all(
                row["regionally_eligible"]
                or (
                    row["recommendation"] == "not_recommended"
                    and row["suitability_score"] <= 54
                    and "unsupported_region" in row["applied_gates"]
                )
                for row in rows
            ),
        },
        "sensitivity": sensitivity,
        "review_notes": [
            "The audit corrected one monotonicity defect: limited irrigation previously scored below no irrigation in 34 site-crop comparisons.",
            "Confidence is normalized over evidence factors applicable to the evaluation mode and crop policy; non-applicable short-range or informational factors do not create false missingness.",
            "Missing expected evidence still lowers confidence, while suitability and evidence confidence remain separate outputs.",
            "Crops without scoreable numeric heat thresholds receive an informational warning; the engine does not invent a heat penalty.",
            "Forage sorghum and sorghum-sudangrass ties reflect materially similar scoreable catalog fields, not nondeterministic sorting.",
        ],
    }
    save_json(REPORT_PATH, report)
    print(f"Reviewed {len(sensitivity)} active factors across {len(inputs)} scenario runs each")
    print(f"Saved sensitivity report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
