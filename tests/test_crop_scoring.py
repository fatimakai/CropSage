import copy
import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scoring.score_crops import (
    irrigation_availability_score,
    parse_numeric_range,
    ph_score,
    score_crops,
    temperature_score,
    tier_score,
)
from scoring.validate_recommendations import validate_ranking_contract


ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class DeterministicCropScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = load_json(ROOT / "data/evidence/plainview_evidence_bundle.json")
        cls.profile = load_json(ROOT / "data/farm-profile/plainview_aug_2026.sample.json")
        cls.config = load_json(ROOT / "data/scoring/crop_scoring_config.json")
        cls.schema = load_json(ROOT / "data/scoring/recommendation.schema.json")
        cls.saved_output = load_json(ROOT / "data/scoring/plainview_crop_recommendations.json")

    def result(self, crop_id, output=None):
        output = output or self.saved_output
        return next(item for item in output["rankings"] if item["crop_id"] == crop_id)

    def factor(self, crop_id, factor_id, output=None):
        return next(item for item in self.result(crop_id, output)["factors"] if item["factor_id"] == factor_id)

    def test_weights_total_exactly_100(self):
        self.assertTrue(math.isclose(sum(self.config["weights_percent"].values()), 100.0))
        self.assertEqual(self.config["weights_percent"]["frost_free_season"], 0.0)

    def test_output_conforms_to_schema(self):
        errors = list(Draft202012Validator(self.schema).iter_errors(self.saved_output))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_saved_output_is_deterministic(self):
        self.assertEqual(self.saved_output, score_crops(self.evidence, self.profile, self.config))

    def test_all_22_crops_are_ranked_once(self):
        rankings = self.saved_output["rankings"]
        self.assertEqual(len(rankings), 22)
        self.assertEqual(len({item["crop_id"] for item in rankings}), 22)
        self.assertEqual([item["overall_rank"] for item in rankings], list(range(1, 23)))
        self.assertNotIn("rank", rankings[0])
        self.assertTrue(all(item["factors"] and len(item["factors"]) == 18 for item in rankings))

    def test_finalized_ineligible_crop_ranking_contract(self):
        validation = validate_ranking_contract(self.saved_output)
        self.assertTrue(validation["eligibility_ranking_policy_passed"], validation)
        self.assertEqual(validation["eligible_crop_count"], 21)
        self.assertEqual(validation["ineligible_crop_count"], 1)
        rice = self.saved_output["rankings"][-1]
        self.assertEqual(rice["crop_id"], "long_grain_rice")
        self.assertFalse(rice["regionally_eligible"])
        self.assertEqual(rice["overall_rank"], 22)
        self.assertIsNone(rice["eligible_rank"])
        self.assertEqual(rice["recommendation"], "not_recommended")
        self.assertLessEqual(rice["suitability_score"], 54.0)
        self.assertIn("unsupported_region", {item["gate"] for item in rice["applied_gates"]})

    def test_requested_crop_result_uses_the_same_contract(self):
        profile = copy.deepcopy(self.profile)
        profile["requested_crop_id"] = "long_grain_rice"
        output = score_crops(self.evidence, profile, self.config)
        requested = output["requested_crop_result"]
        self.assertEqual(requested, self.result("long_grain_rice", output))
        self.assertIn("regionally_eligible", requested)
        self.assertIn("overall_rank", requested)
        self.assertIn("eligible_rank", requested)
        self.assertIn("applied_gates", requested)
        self.assertNotIn("rank", requested)
        errors = list(Draft202012Validator(self.schema).iter_errors(output))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_temperature_and_heat_tier_boundaries(self):
        self.assertEqual(temperature_score(20, {"min": 15, "max": 25}, self.config), (100.0, 0.0))
        self.assertEqual(temperature_score(27, {"min": 15, "max": 25}, self.config), (80.0, 2.0))
        self.assertEqual(temperature_score(31, {"min": 15, "max": 25}, self.config), (20.0, 6.0))
        tiers = self.config["heat_exceedance_fraction_tiers"]
        self.assertEqual(tier_score(0.0, tiers, "max_fraction"), 100.0)
        self.assertEqual(tier_score(0.01, tiers, "max_fraction"), 90.0)
        self.assertEqual(tier_score(0.0501, tiers, "max_fraction"), 40.0)

    def test_ph_tiers_and_numeric_range_parsing(self):
        self.assertEqual(parse_numeric_range("186.8-266.4"), (186.8, 266.4))
        self.assertEqual(ph_score(6.5, {"min": 6.0, "max": 7.0}), (100.0, 0.0))
        self.assertEqual(ph_score(7.5, {"min": 6.0, "max": 7.0}), (75.0, 0.5))
        self.assertEqual(ph_score(8.2, {"min": 6.0, "max": 7.0}), (15.0, 1.1999999999999993))

    def test_irrigation_access_is_monotonic_for_every_requirement(self):
        requirements = ("often_rainfed", "conditional", "recommended", "usually_required")
        no_irrigation = {"availability": "no", "reliability": "not_applicable"}
        for reliability in ("unreliable", "seasonal", "limited", "unknown", "reliable"):
            available = {"availability": "yes", "reliability": reliability}
            for requirement in requirements:
                self.assertGreaterEqual(
                    irrigation_availability_score(available, requirement),
                    irrigation_availability_score(no_irrigation, requirement),
                    f"{reliability}:{requirement}",
                )

    def test_catalog_temperature_ranges_are_normalized(self):
        for crop in self.evidence["crop_evidence"]:
            optimal = crop["profile"]["optimal_temperature_range_c"]
            self.assertIsNotNone(optimal["min"], crop["crop_id"])
            self.assertIsNotNone(optimal["max"], crop["crop_id"])

    def test_informational_heat_threshold_never_penalizes(self):
        for factor_id in ("fortyguard_threshold_exceedance", "fortyguard_heat_persistence"):
            item = self.factor("fresh_market_spinach", factor_id)
            self.assertFalse(item["available"])
            self.assertIsNone(item["weighted_points"])
            self.assertEqual(item["scoring_use"], "informational_only")

    def test_unsupported_region_and_far_window_caps(self):
        rice = self.result("long_grain_rice")
        self.assertLessEqual(rice["suitability_score"], 54.0)
        self.assertIn("unsupported_region", {item["gate"] for item in rice["applied_caps"]})
        self.assertIn("unsupported_region", {item["gate"] for item in rice["applied_gates"]})
        cotton = self.result("upland_cotton")
        self.assertLessEqual(cotton["suitability_score"], 54.0)
        self.assertIn("far_outside_planting_window", {item["gate"] for item in cotton["applied_caps"]})

    def test_missing_irrigation_lowers_confidence_not_score_as_zero(self):
        profile = copy.deepcopy(self.profile)
        del profile["irrigation"]
        output = score_crops(self.evidence, profile, self.config)
        item = next(row for row in output["rankings"] if row["crop_id"] == "fresh_market_spinach")
        irrigation = next(row for row in item["factors"] if row["factor_id"] == "irrigation_availability")
        self.assertFalse(irrigation["available"])
        self.assertIsNone(irrigation["score"])
        self.assertLess(item["confidence_score"], self.result("fresh_market_spinach")["confidence_score"])

    def test_laboratory_ph_overrides_ssurgo(self):
        profile = copy.deepcopy(self.profile)
        profile["soil_overrides"] = {
            "laboratory_ph": {"value": 6.5, "tested_at": "2026-08-20"}
        }
        output = score_crops(self.evidence, profile, self.config)
        item = next(row for row in output["rankings"] if row["crop_id"] == "upland_cotton")
        ph = next(row for row in item["factors"] if row["factor_id"] == "soil_ph")
        self.assertEqual(ph["score"], 100.0)
        self.assertEqual(ph["evidence"]["sources"][0], "laboratory_measurement")

    def test_future_period_switches_to_planning_mode(self):
        profile = copy.deepcopy(self.profile)
        profile["planting"] = {"planned_month": "2027-05", "flexibility_days": 30}
        output = score_crops(self.evidence, profile, self.config)
        self.assertEqual(output["evaluation_mode"], "planning")
        item = next(row for row in output["rankings"] if row["crop_id"] == "upland_cotton")
        by_id = {factor["factor_id"]: factor for factor in item["factors"]}
        self.assertFalse(by_id["open_meteo_heat_frost"]["available"])
        self.assertFalse(by_id["forecast_water_balance"]["available"])
        self.assertFalse(by_id["current_soil_moisture"]["available"])

    def test_profile_must_match_evidence_location(self):
        profile = copy.deepcopy(self.profile)
        profile["location"]["latitude"] += 0.01
        with self.assertRaisesRegex(ValueError, "coordinates do not match"):
            score_crops(self.evidence, profile, self.config)

    def test_scores_are_finite_and_in_range(self):
        for crop in self.saved_output["rankings"]:
            self.assertTrue(math.isfinite(crop["suitability_score"]))
            self.assertGreaterEqual(crop["suitability_score"], 0)
            self.assertLessEqual(crop["suitability_score"], 100)
            self.assertGreaterEqual(crop["confidence_score"], 0)
            self.assertLessEqual(crop["confidence_score"], 100)


if __name__ == "__main__":
    unittest.main()
