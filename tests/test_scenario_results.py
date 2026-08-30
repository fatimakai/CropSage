import csv
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scoring.score_crops import score_crops
from scoring.validate_recommendations import validate_ranking_contract
from scripts.run_scenario_matrix import document_hash


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "data" / "scenarios"
MANIFEST_PATH = SCENARIO_ROOT / "scenario_manifest.json"
AGGREGATE_PATH = SCENARIO_ROOT / "scenario_results.json"
CSV_PATH = SCENARIO_ROOT / "scenario_summary.csv"
REPORT_PATH = SCENARIO_ROOT / "scenario_validation_report.json"
SCHEMA_PATH = ROOT / "data" / "scoring" / "recommendation.schema.json"
CONFIG_PATH = ROOT / "data" / "scoring" / "crop_scoring_config.json"


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class ScenarioResultMatrixContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.aggregate = load_json(AGGREGATE_PATH)
        cls.report = load_json(REPORT_PATH)
        cls.schema = load_json(SCHEMA_PATH)
        cls.config = load_json(CONFIG_PATH)
        cls.outputs = {}
        for run in cls.report["runs"]:
            key = (run["site_id"], run["scenario_type"])
            cls.outputs[key] = load_json(ROOT / run["output_path"])
        with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
            cls.csv_rows = list(csv.DictReader(handle))

    def test_exactly_75_outputs_and_1650_unique_crop_results_exist(self):
        self.assertEqual(self.aggregate["run_count"], 75)
        self.assertEqual(self.aggregate["crop_result_count"], 1650)
        self.assertEqual(len(self.outputs), 75)
        self.assertEqual(len(self.aggregate["results"]), 1650)
        self.assertEqual(len(self.csv_rows), 1650)
        keys = {
            (row["site_id"], row["scenario_type"], row["crop_id"])
            for row in self.aggregate["results"]
        }
        self.assertEqual(len(keys), 1650)

    def test_all_outputs_conform_to_schema_and_ranking_policy(self):
        validator = Draft202012Validator(self.schema, format_checker=FormatChecker())
        for key, output in self.outputs.items():
            errors = list(validator.iter_errors(output))
            self.assertEqual(
                errors,
                [],
                f"{key}: " + "\n".join(error.message for error in errors),
            )
            ranking = validate_ranking_contract(output)
            self.assertTrue(ranking["eligibility_ranking_policy_passed"], f"{key}: {ranking}")

    def test_saved_outputs_match_fresh_deterministic_engine_runs(self):
        for site in self.manifest["sites"]:
            evidence = load_json(ROOT / site["evidence_bundle_path"])
            for scenario in site["scenarios"]:
                profile = load_json(ROOT / scenario["profile_path"])
                expected = score_crops(evidence, profile, self.config)
                actual = self.outputs[(site["site_id"], scenario["scenario_type"])]
                self.assertEqual(actual, expected, profile["profile_id"])

    def test_validation_report_hashes_and_checks_match_outputs(self):
        self.assertEqual(self.report["status"], "validated")
        self.assertTrue(all(self.report["global_checks"].values()))
        self.assertEqual(self.report["actual_run_count"], 75)
        self.assertEqual(self.report["actual_crop_result_count"], 1650)
        for run in self.report["runs"]:
            output = self.outputs[(run["site_id"], run["scenario_type"])]
            self.assertEqual(run["output_sha256"], document_hash(output), run["profile_id"])
            self.assertTrue(run["schema_valid"], run["profile_id"])
            self.assertTrue(run["ranking_policy_valid"], run["profile_id"])
            self.assertTrue(all(run["behavior_checks"].values()), run["profile_id"])
            self.assertTrue(run["passed"], run["profile_id"])

    def test_reliable_irrigation_never_scores_below_no_irrigation(self):
        by_key = {
            (row["site_id"], row["scenario_type"], row["crop_id"]): row
            for row in self.aggregate["results"]
        }
        sites = {row["site_id"] for row in self.aggregate["results"]}
        crops = {row["crop_id"] for row in self.aggregate["results"]}
        for site_id in sites:
            for crop_id in crops:
                reliable = by_key[(site_id, "reliable_irrigation", crop_id)]
                none = by_key[(site_id, "no_irrigation", crop_id)]
                self.assertGreaterEqual(
                    reliable["suitability_score"],
                    none["suitability_score"],
                    f"{site_id}:{crop_id}",
                )

    def test_limited_irrigation_never_scores_below_no_irrigation(self):
        by_key = {
            (row["site_id"], row["scenario_type"], row["crop_id"]): row
            for row in self.aggregate["results"]
        }
        sites = {row["site_id"] for row in self.aggregate["results"]}
        crops = {row["crop_id"] for row in self.aggregate["results"]}
        for site_id in sites:
            for crop_id in crops:
                limited = by_key[(site_id, "in_season_baseline", crop_id)]
                none = by_key[(site_id, "no_irrigation", crop_id)]
                self.assertGreaterEqual(
                    limited["suitability_score"],
                    none["suitability_score"],
                    f"{site_id}:{crop_id}",
                )

    def test_out_of_season_requested_crops_receive_the_planting_gate(self):
        rows = [
            row
            for row in self.aggregate["results"]
            if row["scenario_type"] == "out_of_season" and row["is_requested_crop"]
        ]
        self.assertEqual(len(rows), 15)
        for row in rows:
            self.assertLessEqual(row["suitability_score"], 54, row["profile_id"])
            self.assertIn("far_outside_planting_window", row["applied_gates"], row["profile_id"])

    def test_ineligible_crops_are_retained_but_never_recommended(self):
        ineligible = [
            row for row in self.aggregate["results"] if not row["regionally_eligible"]
        ]
        self.assertGreater(len(ineligible), 0)
        for row in ineligible:
            self.assertIsNone(row["eligible_rank"], row["profile_id"])
            self.assertEqual(row["recommendation"], "not_recommended", row["profile_id"])
            self.assertLessEqual(row["suitability_score"], 54, row["profile_id"])
            self.assertIn("unsupported_region", row["applied_gates"], row["profile_id"])


if __name__ == "__main__":
    unittest.main()
