import json
import math
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
REGIONS_DIR = ROOT / "data" / "evidence" / "regions"
SCHEMA_PATH = ROOT / "data" / "evidence" / "evidence_bundle.schema.json"
MANIFEST_PATH = ROOT / "data" / "regions" / "texas_region_sites.json"
CATALOG_PATH = ROOT / "data" / "crop-catalog" / "catalog.json"
SUMMARY_PATH = REGIONS_DIR / "collection_summary.json"
PROVIDERS = {"fortyguard", "nasa_power", "open_meteo", "ssurgo"}
EXPECTED_UNITS = {
    "air_temperature": "degC",
    "precipitation": "mm",
    "relative_humidity": "percent",
    "wind_speed": "m/s",
    "solar_radiation": "MJ/m^2/day",
    "photosynthetically_active_radiation": "MJ/m^2/day",
    "soil_temperature": "degC",
    "volumetric_soil_moisture": "m^3/m^3",
    "available_water_storage": "mm",
    "depth": "cm",
    "heat_exposure": "hour",
    "ph": "dimensionless",
}
LEGACY_TEXTURE_ABBREVIATIONS = {"fsl", "lfs"}


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def invalid_values(value, path="$"):
    problems = []
    if isinstance(value, float) and not math.isfinite(value):
        problems.append(path)
    elif isinstance(value, str) and value.strip().lower() in {
        "nan",
        "infinity",
        "-infinity",
        "inf",
        "-inf",
    }:
        problems.append(path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            problems.extend(invalid_values(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            problems.extend(invalid_values(item, f"{path}.{key}"))
    return problems


class AllRegionEvidenceBundleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(SCHEMA_PATH)
        cls.manifest = load_json(MANIFEST_PATH)
        cls.catalog = load_json(CATALOG_PATH)
        cls.summary = load_json(SUMMARY_PATH)
        cls.sites = {site["site_id"]: site for site in cls.manifest["sites"]}
        cls.bundle_paths = {
            path.parent.name: path
            for path in REGIONS_DIR.glob("*/evidence_bundle.json")
        }
        cls.bundles = {
            site_id: load_json(path) for site_id, path in cls.bundle_paths.items()
        }
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_exactly_one_bundle_exists_for_each_manifest_site(self):
        self.assertEqual(self.manifest["site_count"], 15)
        self.assertEqual(len(self.sites), 15)
        self.assertEqual(set(self.bundle_paths), set(self.sites))

    def test_all_bundles_conform_to_evidence_schema_1_2(self):
        Draft202012Validator.check_schema(self.schema)
        for site_id, bundle in self.bundles.items():
            errors = sorted(
                self.validator.iter_errors(bundle),
                key=lambda error: list(error.absolute_path),
            )
            self.assertEqual(
                errors,
                [],
                f"{site_id}: " + "\n".join(error.message for error in errors),
            )
            self.assertEqual(bundle["schema_version"], "1.2.0", site_id)

    def test_bundle_location_matches_manifest_identity(self):
        for site_id, site in self.sites.items():
            location = self.bundles[site_id]["location"]
            self.assertEqual(location["farm_id"], site_id, site_id)
            self.assertAlmostEqual(location["latitude"], site["location"]["latitude"], places=6, msg=site_id)
            self.assertAlmostEqual(location["longitude"], site["location"]["longitude"], places=6, msg=site_id)
            self.assertEqual(location["texas_region_id"], site["parent_region_id"], site_id)
            self.assertEqual(location["timezone"], site["timezone"], site_id)

    def test_all_four_providers_are_aligned_and_fresh(self):
        for site_id, bundle in self.bundles.items():
            self.assertEqual(set(bundle["provenance"]), PROVIDERS, site_id)
            bundle_time = datetime.fromisoformat(bundle["generated_at"])
            for provider, source in bundle["provenance"].items():
                self.assertTrue(source["location_match"], f"{site_id}:{provider}")
                self.assertTrue(source["freshness"]["passed"], f"{site_id}:{provider}")
                self.assertEqual(source["freshness"]["status"], "fresh", f"{site_id}:{provider}")
                self.assertLessEqual(
                    source["freshness"]["age_hours"],
                    source["freshness"]["max_age_hours"],
                    f"{site_id}:{provider}",
                )
                self.assertLessEqual(datetime.fromisoformat(source["generated_at"]), bundle_time, f"{site_id}:{provider}")

    def test_all_bundles_contain_the_same_22_catalog_crops(self):
        catalog_ids = [crop["crop_id"] for crop in self.catalog["crops"]]
        self.assertEqual(len(catalog_ids), 22)
        self.assertEqual(len(set(catalog_ids)), 22)
        for site_id, bundle in self.bundles.items():
            bundle_ids = [crop["crop_id"] for crop in bundle["crop_evidence"]]
            self.assertEqual(bundle_ids, catalog_ids, site_id)
            self.assertEqual(bundle["catalog"]["crop_ids"], catalog_ids, site_id)
            self.assertEqual(bundle["catalog"]["crop_count"], 22, site_id)

    def test_regional_eligibility_is_derived_from_the_selected_catalog_region(self):
        for site_id, bundle in self.bundles.items():
            expected_region = self.sites[site_id]["parent_region_id"]
            for crop in bundle["crop_evidence"]:
                regional = crop["profile"]["regional_suitability"]
                self.assertEqual(regional["region_id"], expected_region, f"{site_id}:{crop['crop_id']}")
                self.assertEqual(
                    crop["regionally_eligible"],
                    regional["rating"] != "not_supported",
                    f"{site_id}:{crop['crop_id']}",
                )

    def test_required_provider_evidence_is_ready_for_scoring(self):
        for site_id, bundle in self.bundles.items():
            evidence = bundle["location_evidence"]
            heat = evidence["fortyguard_heat"]
            self.assertGreaterEqual(len(heat["windows"]), 1, site_id)
            self.assertEqual(heat["total_null_values"], 0, site_id)
            self.assertEqual(len(evidence["nasa_power_climate"]["monthly_summary"]), 12, site_id)
            self.assertGreaterEqual(len(evidence["open_meteo_weather"]["recent_complete_days"]), 7, site_id)
            self.assertGreaterEqual(len(evidence["open_meteo_weather"]["forecast_daily"]), 7, site_id)
            self.assertGreaterEqual(len(evidence["ssurgo_soil"]["horizons"]), 1, site_id)

    def test_fortyguard_temperature_fields_have_correct_spatial_and_period_semantics(self):
        required = {
            "minimum_tile_average_temperature_c",
            "maximum_tile_average_temperature_c",
            "period_minimum_temperature_c",
            "period_maximum_temperature_c",
        }
        legacy = {"minimum_temperature_c", "maximum_temperature_c"}
        for site_id, bundle in self.bundles.items():
            for window in bundle["location_evidence"]["fortyguard_heat"]["windows"]:
                self.assertTrue(required.issubset(window), site_id)
                self.assertTrue(legacy.isdisjoint(window), site_id)
                self.assertLessEqual(
                    window["minimum_tile_average_temperature_c"],
                    window["mean_temperature_c"],
                    site_id,
                )
                self.assertLessEqual(
                    window["mean_temperature_c"],
                    window["maximum_tile_average_temperature_c"],
                    site_id,
                )
                self.assertLessEqual(
                    window["period_minimum_temperature_c"],
                    window["period_maximum_temperature_c"],
                    site_id,
                )

    def test_ssurgo_texture_abbreviations_are_expanded(self):
        for site_id, bundle in self.bundles.items():
            soil = bundle["location_evidence"]["ssurgo_soil"]
            self.assertNotIn(soil["surface_texture"].strip().lower(), LEGACY_TEXTURE_ABBREVIATIONS, site_id)

    def test_units_values_and_embedded_validation_are_clean(self):
        for site_id, bundle in self.bundles.items():
            self.assertEqual(bundle["units"], EXPECTED_UNITS, site_id)
            self.assertEqual(invalid_values(bundle), [], site_id)
            json.dumps(bundle, allow_nan=False)
            self.assertTrue(bundle["validation"]["all_passed"], site_id)
            self.assertEqual(bundle["validation"]["invalid_numeric_value_count"], 0, site_id)
            self.assertTrue(all(check["passed"] for check in bundle["validation"]["checks"]), site_id)

    def test_collection_summary_matches_validated_bundle_set(self):
        self.assertEqual(self.summary["requested_site_count"], 15)
        self.assertEqual(self.summary["validated_site_count"], 15)
        self.assertEqual(self.summary["failed_site_count"], 0)
        self.assertEqual(set(self.summary["sites"]), set(self.sites))
        for site_id, result in self.summary["sites"].items():
            self.assertEqual(result["status"], "validated", site_id)
            self.assertEqual(result["crop_count"], 22, site_id)
            self.assertTrue(result["validation_passed"], site_id)


if __name__ == "__main__":
    unittest.main()
