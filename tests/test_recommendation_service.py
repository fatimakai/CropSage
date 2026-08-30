from __future__ import annotations

import unittest

from services.recommendation_service import (
    RecommendationServiceError,
    get_planting_guidance,
    recommend_crops,
)


class RecommendationServiceContract(unittest.TestCase):
    def test_planting_guidance_needs_no_year_or_irrigation(self) -> None:
        result = get_planting_guidance(
            latitude=28.89,
            longitude=-98.57,
            crop_id="upland_cotton",
            location_label="Poteet, Texas",
        )
        self.assertEqual(result["result_type"], "planting_guidance")
        self.assertEqual(result["guidance"]["planting_windows"], ["Mar-May"])

    def test_poteet_request_resolves_to_nearest_cached_bundle(self) -> None:
        response = recommend_crops(
            latitude=28.89,
            longitude=-98.57,
            planting_month="2026-10",
            irrigation_availability="yes",
            irrigation_reliability="reliable",
            irrigation_method="drip",
            crop_id="fresh_market_spinach",
            location_label="Near Poteet, Texas",
        )
        resolution = response["location_resolution"]
        result = response["recommendation"]
        self.assertEqual(response["status"], "validated")
        self.assertEqual(resolution["site_id"], "central_south_poteet")
        self.assertEqual(resolution["parent_catalog_region_id"], "central_south_winter_garden")
        self.assertLess(resolution["distance_km"], 5)
        self.assertFalse(resolution["exact_cached_location_match"])
        self.assertEqual(result["scoring_version"], "1.0.1")
        self.assertEqual(len(result["rankings"]), 22)
        self.assertEqual(result["requested_crop_id"], "fresh_market_spinach")
        self.assertEqual(result["requested_crop_result"]["crop_id"], "fresh_market_spinach")
        self.assertEqual(response["request"]["location"]["longitude"], -98.57)
        self.assertEqual(result["location"]["longitude"], -98.6)

    def test_exact_representative_coordinate_is_not_marked_as_a_proxy(self) -> None:
        response = recommend_crops(
            latitude=34.18,
            longitude=-101.79,
            planting_month="2026-08",
            irrigation_availability="no",
        )
        resolution = response["location_resolution"]
        self.assertEqual(resolution["site_id"], "plains_south_plainview")
        self.assertEqual(resolution["distance_km"], 0.0)
        self.assertTrue(resolution["exact_cached_location_match"])
        self.assertEqual(resolution["proxy_quality"], "exact_or_adjacent")

    def test_soil_test_ph_and_texture_override_cached_ssurgo_values(self) -> None:
        response = recommend_crops(
            latitude=34.18,
            longitude=-101.79,
            planting_month="2026-08",
            irrigation_availability="yes",
            crop_id="upland_cotton",
            soil_test_values={
                "ph": 6.5,
                "tested_at": "2026-08-20",
                "laboratory_name": "Test laboratory",
                "texture": "fine sandy loam",
            },
        )
        crop = response["recommendation"]["requested_crop_result"]
        factors = {factor["factor_id"]: factor for factor in crop["factors"]}
        self.assertEqual(factors["soil_ph"]["evidence"]["values"]["ph"], 6.5)
        self.assertIn("Laboratory pH overrides", factors["soil_ph"]["reason"])
        self.assertEqual(
            factors["soil_texture"]["evidence"]["values"]["texture"],
            "fine sandy loam",
        )
        self.assertEqual(factors["soil_texture"]["evidence"]["sources"][0], "farmer_measurement")

    def test_request_without_crop_returns_all_ranked_alternatives(self) -> None:
        response = recommend_crops(
            latitude=31.50,
            longitude=-106.17,
            planting_month="2026-09",
            irrigation_availability="unknown",
        )
        result = response["recommendation"]
        self.assertIsNone(result["requested_crop_id"])
        self.assertIsNone(result["requested_crop_result"])
        self.assertEqual([item["overall_rank"] for item in result["rankings"]], list(range(1, 23)))

    def test_invalid_inputs_fail_before_scoring(self) -> None:
        cases = [
            {"latitude": 40, "longitude": -100, "planting_month": "2026-08", "irrigation_availability": "yes"},
            {"latitude": 34.18, "longitude": -101.79, "planting_month": "August", "irrigation_availability": "yes"},
            {"latitude": 34.18, "longitude": -101.79, "planting_month": "2026-08", "irrigation_availability": "sometimes"},
            {"latitude": 34.18, "longitude": -101.79, "planting_month": "2026-08", "irrigation_availability": "yes", "crop_id": "imaginary_crop"},
            {"latitude": 34.18, "longitude": -101.79, "planting_month": "2026-08", "irrigation_availability": "yes", "soil_test_values": {"ph": 6.5}},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(RecommendationServiceError):
                    recommend_crops(**kwargs)

    def test_identical_requests_are_deterministic(self) -> None:
        request = {
            "latitude": 29.56,
            "longitude": -96.30,
            "planting_month": "2026-08",
            "irrigation_availability": "yes",
            "irrigation_reliability": "limited",
            "crop_id": "long_grain_rice",
        }
        self.assertEqual(recommend_crops(**request), recommend_crops(**request))


if __name__ == "__main__":
    unittest.main()
