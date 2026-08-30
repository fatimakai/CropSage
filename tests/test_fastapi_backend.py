from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from api.main import app


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "handoff" / "fatima_scoring_migrations"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scoring_request() -> dict:
    return {
        "farm_profile": load_json(HANDOFF / "sample_engine_input.json"),
        "evidence_bundle": load_json(HANDOFF / "sample_evidence_bundle.json"),
        "scoring_config": load_json(HANDOFF / "sample_scoring_config.json"),
    }


class FastApiBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_health_reports_finalized_versions(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "backend-api")
        self.assertEqual(body["contracts"]["evidence_bundle"], "1.2.0")
        self.assertEqual(body["contracts"]["crop_catalog"], "1.1.0")
        self.assertEqual(body["contracts"]["scoring_engine"], "1.0.0")

    def test_finalized_score_contract_returns_valid_22_crop_output(self) -> None:
        response = self.client.post("/v1/recommendations/score", json=scoring_request())
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()

        schema = load_json(ROOT / "data" / "scoring" / "recommendation.schema.json")
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)

        rankings = result["rankings"]
        self.assertEqual(len(rankings), 22)
        self.assertEqual(len({item["crop_id"] for item in rankings}), 22)
        self.assertEqual([item["overall_rank"] for item in rankings], list(range(1, 23)))
        self.assertEqual(result["status"], "validated")
        for crop in rankings:
            self.assertIn("suitability_score", crop)
            self.assertIn("confidence_score", crop)

        ineligible = [item for item in rankings if not item["regionally_eligible"]]
        self.assertTrue(ineligible)
        for crop in ineligible:
            self.assertIsNone(crop["eligible_rank"])
            self.assertLessEqual(crop["suitability_score"], 54)
            self.assertEqual(crop["recommendation"], "not_recommended")
            self.assertIn("unsupported_region", {gate["gate"] for gate in crop["applied_gates"]})

    def test_unvalidated_evidence_cannot_be_displayed(self) -> None:
        payload = scoring_request()
        payload["evidence_bundle"] = copy.deepcopy(payload["evidence_bundle"])
        payload["evidence_bundle"]["validation"]["all_passed"] = False
        response = self.client.post("/v1/recommendations/score", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("rankings", response.text)

    def test_contract_error_does_not_echo_secret_like_input(self) -> None:
        marker = "do-not-echo-this-secret-value"
        payload = scoring_request()
        payload["api_key"] = marker
        response = self.client.post("/v1/recommendations/score", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_high_level_recommendation_uses_cached_regional_bundle(self) -> None:
        response = self.client.post(
            "/v1/recommendations",
            json={
                "latitude": 28.89,
                "longitude": -98.57,
                "planting_month": "2026-10",
                "irrigation_availability": "yes",
                "irrigation_reliability": "reliable",
                "irrigation_method": "drip",
                "crop_id": "fresh_market_spinach",
                "location_label": "Poteet, Texas",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "validated")
        self.assertEqual(len(result["recommendation"]["rankings"]), 22)
        self.assertEqual(result["recommendation"]["requested_crop_id"], "fresh_market_spinach")

    def test_execution_package_contains_exact_persistence_contracts(self) -> None:
        profile = load_json(HANDOFF / "sample_engine_input.json")
        response = self.client.post(
            "/v1/recommendations/execute",
            json={"farm_profile": profile},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["evidence_bundle"]["schema_version"], "1.2.0")
        self.assertEqual(result["scoring_config"]["status"], "frozen")
        self.assertEqual(len(result["recommendation"]["rankings"]), 22)
        self.assertTrue(result["validation_report"]["render_allowed"])
        self.assertEqual(result["validation_report"]["errors"], [])
        self.assertIn("source_coordinates", result["location_resolution"])
        self.assertEqual(
            result["farm_profile"]["location"]["latitude"],
            result["evidence_bundle"]["location"]["latitude"],
        )


if __name__ == "__main__":
    unittest.main()
