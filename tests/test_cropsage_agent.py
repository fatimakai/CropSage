from __future__ import annotations

import unittest

from agent.cropsage_agent import CropSageAgent, ExtractedTurn, FailoverGateway


class FakeGateway:
    def __init__(self, turns: list[dict], answers: list[str] | None = None) -> None:
        self.turns = list(turns)
        self.answers = list(answers or [])
        self.extraction_prompts: list[str] = []
        self.generation_prompts: list[str] = []

    def extract(self, prompt: str) -> ExtractedTurn:
        self.extraction_prompts.append(prompt)
        return ExtractedTurn.model_validate(self.turns.pop(0))

    def generate(self, prompt: str) -> str:
        self.generation_prompts.append(prompt)
        return self.answers.pop(0) if self.answers else "Grounded explanation."


class CropSageAgentTests(unittest.TestCase):
    def test_agent_collects_missing_fields_across_turns_then_calls_service(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "crop_id": "fresh_market_spinach",
                    "planting_month": "2026-10",
                    "irrigation_availability": "yes",
                    "irrigation_reliability": "reliable",
                    "irrigation_method": "drip",
                },
                {"intent": "provide_information", "latitude": 28.89, "longitude": -98.57},
            ],
            ["Spinach is recommended, but the evidence confidence is low."],
        )
        agent = CropSageAgent(gateway=gateway)
        first = agent.chat("I want spinach near Poteet in October 2026 with drip irrigation.")
        self.assertEqual(first["status"], "needs_input")
        self.assertEqual(first["missing_fields"], ["location"])
        second = agent.chat("The coordinates are 28.89, -98.57.")
        self.assertEqual(second["status"], "recommendation")
        self.assertEqual(second["recommendation"]["recommendation"]["scoring_version"], "1.0.0")
        self.assertEqual(second["recommendation"]["location_resolution"]["site_id"], "central_south_poteet")
        self.assertEqual(second["recommendation"]["recommendation"]["requested_crop_id"], "fresh_market_spinach")

    def test_follow_up_uses_existing_result_without_rerunning_service(self) -> None:
        calls: list[dict] = []

        def fake_service(**kwargs):
            calls.append(kwargs)
            from services.recommendation_service import recommend_crops

            return recommend_crops(**kwargs)

        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "latitude": 34.18,
                    "longitude": -101.79,
                    "planting_month": "2026-08",
                    "irrigation_availability": "no",
                },
                {"intent": "follow_up"},
            ],
            ["Initial explanation.", "The confidence is based on evidence coverage."],
        )
        agent = CropSageAgent(gateway=gateway, recommendation_function=fake_service)
        self.assertEqual(agent.chat("Assess this farm.")["status"], "recommendation")
        response = agent.chat("Why is the confidence lower than suitability?")
        self.assertEqual(response["status"], "answer")
        self.assertEqual(len(calls), 1)
        self.assertIn("Deterministic result JSON", gateway.generation_prompts[-1])

    def test_soil_ph_requires_test_date_before_service_call(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "latitude": 34.18,
                    "longitude": -101.79,
                    "planting_month": "2026-08",
                    "irrigation_availability": "yes",
                    "soil_ph": 6.4,
                }
            ]
        )
        agent = CropSageAgent(gateway=gateway)
        response = agent.chat("My laboratory soil pH is 6.4.")
        self.assertEqual(response["status"], "needs_input")
        self.assertEqual(response["missing_fields"], ["soil_tested_at"])

    def test_reset_clears_collected_inputs_and_result(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "latitude": 34.18,
                    "longitude": -101.79,
                    "planting_month": "2026-08",
                    "irrigation_availability": "unknown",
                },
                {"intent": "reset"},
            ]
        )
        agent = CropSageAgent(gateway=gateway)
        self.assertEqual(agent.chat("Assess Plainview.")["status"], "recommendation")
        response = agent.chat("Clear this assessment.")
        self.assertEqual(response["status"], "needs_input")
        self.assertEqual(response["collected_inputs"], {})
        self.assertIsNone(response["recommendation"])

    def test_agent_returns_safe_error_for_invalid_extracted_crop(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "latitude": 34.18,
                    "longitude": -101.79,
                    "planting_month": "2026-08",
                    "irrigation_availability": "yes",
                    "crop_id": "imaginary_crop",
                }
            ]
        )
        agent = CropSageAgent(gateway=gateway)
        response = agent.chat("Plant an imaginary crop.")
        self.assertEqual(response["status"], "needs_input")
        self.assertIn("22 supported crops", response["message"])

    def test_place_name_is_geocoded_without_farmer_coordinates(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "location_label": "Poteet, Texas",
                    "planting_month": "2026-10",
                    "irrigation_availability": "yes",
                    "crop_id": "fresh_market_spinach",
                }
            ]
        )
        resolver = lambda _: {
            "latitude": 28.89,
            "longitude": -98.57,
            "display_name": "Poteet, Atascosa County, Texas",
            "provider": "test_geocoder",
        }
        agent = CropSageAgent(gateway=gateway, location_resolver=resolver)
        response = agent.chat("Spinach near Poteet in October 2026 with irrigation.")
        self.assertEqual(response["status"], "recommendation")
        self.assertEqual(response["collected_inputs"]["geocoding_provider"], "test_geocoder")

    def test_when_to_plant_does_not_require_year_or_irrigation(self) -> None:
        gateway = FakeGateway(
            [
                {
                    "intent": "provide_information",
                    "request_type": "planting_guidance",
                    "location_label": "Poteet, Texas",
                    "crop_id": "upland_cotton",
                }
            ],
            ["Plant cotton from March through May."],
        )
        resolver = lambda _: {
            "latitude": 28.89,
            "longitude": -98.57,
            "display_name": "Poteet, Texas",
            "provider": "test_geocoder",
        }
        agent = CropSageAgent(gateway=gateway, location_resolver=resolver)
        response = agent.chat("When should I plant cotton near Poteet?")
        self.assertEqual(response["status"], "planting_guidance")
        self.assertEqual(response["recommendation"]["guidance"]["planting_windows"], ["Mar-May"])
        self.assertNotIn("planting_month", response["missing_fields"])

    def test_provider_failure_never_exposes_raw_quota_error(self) -> None:
        class BrokenGateway:
            def extract(self, prompt: str) -> ExtractedTurn:
                raise RuntimeError("429 RESOURCE_EXHAUSTED secret provider detail")

            def generate(self, prompt: str) -> str:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

        agent = CropSageAgent(gateway=BrokenGateway())
        response = agent.chat("I want to plant cotton.")
        self.assertEqual(response["status"], "needs_input")
        self.assertNotIn("429", response["message"])
        self.assertNotIn("RESOURCE_EXHAUSTED", response["message"])

    def test_local_fallback_keeps_planting_guidance_working_without_an_llm(self) -> None:
        class BrokenGateway:
            def extract(self, prompt: str) -> ExtractedTurn:
                raise RuntimeError("both providers exhausted")

            def generate(self, prompt: str) -> str:
                raise RuntimeError("both providers exhausted")

        resolver = lambda _: {
            "latitude": 28.89,
            "longitude": -98.57,
            "display_name": "Poteet, Texas",
            "provider": "test_geocoder",
        }
        agent = CropSageAgent(gateway=BrokenGateway(), location_resolver=resolver)
        response = agent.chat("When should I plant cotton near Poteet, Texas?")
        self.assertEqual(response["status"], "planting_guidance")
        self.assertIn("Mar-May", response["message"])
        self.assertIn("No suitability score", response["message"])

        follow_up = agent.chat("Why is there no score?")
        self.assertEqual(follow_up["status"], "answer")
        self.assertIn("planting month and year", follow_up["message"])

        scored = agent.chat("Score upland cotton for April 2027. I have reliable drip irrigation.")
        self.assertEqual(scored["status"], "recommendation")
        requested = scored["recommendation"]["recommendation"]["requested_crop_result"]
        self.assertEqual(requested["crop_id"], "upland_cotton")
        self.assertGreater(requested["suitability_score"], 0)
        self.assertEqual(scored["language_provider"], "local_fallback")

    def test_failover_gateway_uses_second_provider(self) -> None:
        class BrokenGateway:
            def extract(self, prompt: str) -> ExtractedTurn:
                raise RuntimeError("quota")

            def generate(self, prompt: str) -> str:
                raise RuntimeError("quota")

        fallback = FakeGateway([{"intent": "provide_information", "crop_id": "upland_cotton"}])
        gateway = FailoverGateway([BrokenGateway(), fallback])
        extracted = gateway.extract("farmer message")
        self.assertEqual(extracted.crop_id, "upland_cotton")
        self.assertEqual(gateway.last_provider, "Fake")

    def test_fallback_summary_omits_repeated_proxy_and_certification_text(self) -> None:
        from services.recommendation_service import recommend_crops

        result = recommend_crops(
            latitude=28.89,
            longitude=-98.57,
            planting_month="2026-10",
            irrigation_availability="yes",
        )
        summary = CropSageAgent._fallback_summary(result)
        self.assertNotIn("nearest cached site", summary)
        self.assertNotIn("agronomic certification", summary)
        self.assertNotIn("confidence", summary.casefold())


if __name__ == "__main__":
    unittest.main()
