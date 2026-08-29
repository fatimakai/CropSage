import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "data" / "farm-profile" / "farm_profile.schema.json"
SAMPLE_PATH = ROOT / "data" / "farm-profile" / "poteet_spinach_oct_2026.sample.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class FarmProfileSchemaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(SCHEMA_PATH)
        cls.validator = Draft202012Validator(cls.schema)

    def assert_valid(self, profile):
        errors = sorted(self.validator.iter_errors(profile), key=lambda error: list(error.path))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def assert_invalid(self, profile):
        self.assertTrue(list(self.validator.iter_errors(profile)))

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(self.schema)

    def test_poteet_spinach_sample_is_valid(self):
        self.assert_valid(load_json(SAMPLE_PATH))

    def test_minimal_profile_requires_only_location_and_planting(self):
        self.assert_valid(
            {
                "schema_version": "1.0.0",
                "profile_id": "minimal_profile",
                "location": {"latitude": 34.18, "longitude": -101.76},
                "planting": {"planned_month": "2027-05"},
            }
        )

    def test_location_is_required(self):
        self.assert_invalid(
            {
                "schema_version": "1.0.0",
                "profile_id": "missing_location",
                "planting": {"planned_month": "2027-05"},
            }
        )

    def test_exactly_one_planting_date_or_month_is_required(self):
        base = {
            "schema_version": "1.0.0",
            "profile_id": "bad_planting",
            "location": {"latitude": 34.18, "longitude": -101.76},
        }
        self.assert_invalid({**base, "planting": {}})
        self.assert_invalid(
            {
                **base,
                "planting": {
                    "planned_date": "2027-05-10",
                    "planned_month": "2027-05",
                },
            }
        )

    def test_irrigation_can_be_explicitly_unknown(self):
        self.assert_valid(
            {
                "schema_version": "1.0.0",
                "profile_id": "unknown_irrigation",
                "location": {"latitude": 34.18, "longitude": -101.76},
                "planting": {"planned_month": "2027-05"},
                "irrigation": {"availability": "unknown", "reliability": "unknown"},
            }
        )

    def test_laboratory_ph_must_be_physical(self):
        profile = {
            "schema_version": "1.0.0",
            "profile_id": "invalid_ph",
            "location": {"latitude": 34.18, "longitude": -101.76},
            "planting": {"planned_month": "2027-05"},
            "soil_overrides": {
                "laboratory_ph": {"value": 15.0, "tested_at": "2026-08-20"}
            },
        }
        self.assert_invalid(profile)

    def test_unknown_properties_are_rejected(self):
        profile = {
            "schema_version": "1.0.0",
            "profile_id": "unknown_property",
            "location": {"latitude": 34.18, "longitude": -101.76},
            "planting": {"planned_month": "2027-05"},
            "invented_match": 100,
        }
        self.assert_invalid(profile)


if __name__ == "__main__":
    unittest.main()
