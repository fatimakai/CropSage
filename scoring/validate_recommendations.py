"""Semantic validation for deterministic recommendation rankings."""

from __future__ import annotations

from typing import Any


def _score_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    suitability = item.get("suitability_score")
    return (
        suitability is None,
        -(suitability if suitability is not None else 0.0),
        -float(item["confidence_score"]),
        item["crop_id"],
    )


def validate_ranking_contract(
    output: dict[str, Any], expected_crop_count: int = 22, ineligible_score_cap: float = 54.0
) -> dict[str, Any]:
    """Return machine-readable checks for the finalized eligibility/ranking policy."""

    rankings = output.get("rankings", [])
    eligible = [item for item in rankings if item.get("regionally_eligible") is True]
    ineligible = [item for item in rankings if item.get("regionally_eligible") is False]
    overall_ranks = [item.get("overall_rank") for item in rankings]
    eligible_ranks = [item.get("eligible_rank") for item in eligible]
    eligibility_flags = [item.get("regionally_eligible") for item in rankings]

    checks = {
        "crop_count_valid": len(rankings) == expected_crop_count,
        "unique_crop_count_valid": len({item.get("crop_id") for item in rankings}) == expected_crop_count,
        "overall_rank_unique": len(set(overall_ranks)) == expected_crop_count,
        "rank_sequence_valid": overall_ranks == list(range(1, expected_crop_count + 1)),
        "eligibility_ordering_valid": eligibility_flags == ([True] * len(eligible) + [False] * len(ineligible)),
        "within_group_sort_valid": eligible == sorted(eligible, key=_score_sort_key)
        and ineligible == sorted(ineligible, key=_score_sort_key),
        "eligible_rank_sequence_valid": eligible_ranks == list(range(1, len(eligible) + 1)),
        "ineligible_rank_null_valid": all(item.get("eligible_rank") is None for item in ineligible),
        "ineligible_suitability_cap_valid": all(
            item.get("suitability_score") is not None
            and float(item["suitability_score"]) <= ineligible_score_cap
            for item in ineligible
        ),
        "ineligible_recommendation_valid": all(
            item.get("recommendation") == "not_recommended" for item in ineligible
        ),
        "unsupported_region_gate_valid": all(
            "unsupported_region" in {gate.get("gate") for gate in item.get("applied_gates", [])}
            for item in ineligible
        ),
    }
    return {
        "ranking_count": len(rankings),
        "unique_crop_count": len({item.get("crop_id") for item in rankings}),
        "expected_crop_count": expected_crop_count,
        "eligible_crop_count": len(eligible),
        "ineligible_crop_count": len(ineligible),
        **checks,
        "eligibility_ranking_policy_passed": all(checks.values()),
    }
