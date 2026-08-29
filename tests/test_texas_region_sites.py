import json
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data/regions/texas_region_sites.json"
SCHEMA_PATH = ROOT / "data/regions/texas_region_sites.schema.json"
CATALOG_PATH = ROOT / "data/crop-catalog/catalog.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class TexasRegionSiteManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.schema = load_json(SCHEMA_PATH)
        cls.catalog = load_json(CATALOG_PATH)

    def test_schema_is_valid_and_manifest_conforms(self):
        Draft202012Validator.check_schema(self.schema)
        errors = list(
            Draft202012Validator(
                self.schema, format_checker=FormatChecker()
            ).iter_errors(self.manifest)
        )
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_manifest_uses_current_catalog_regions(self):
        catalog_regions = {region["region_id"] for region in self.catalog["regions"]}
        manifest_regions = {site["parent_region_id"] for site in self.manifest["sites"]}
        self.assertEqual(self.manifest["catalog_version"], self.catalog["catalog_version"])
        self.assertEqual(manifest_regions, catalog_regions)

    def test_exactly_three_sites_cover_each_parent_region(self):
        counts = Counter(site["parent_region_id"] for site in self.manifest["sites"])
        self.assertEqual(len(self.manifest["sites"]), 15)
        self.assertEqual(set(counts.values()), {3})
        self.assertEqual(self.manifest["site_count"], 15)

    def test_site_ids_and_coordinates_are_unique(self):
        site_ids = [site["site_id"] for site in self.manifest["sites"]]
        coordinates = [
            (site["location"]["latitude"], site["location"]["longitude"])
            for site in self.manifest["sites"]
        ]
        self.assertEqual(len(site_ids), len(set(site_ids)))
        self.assertEqual(len(coordinates), len(set(coordinates)))

    def test_every_coordinate_has_documented_cdl_verification(self):
        disallowed_classes = {
            "Developed/Open Space",
            "Developed/Low Intensity",
            "Developed/Med Intensity",
            "Developed/High Intensity",
            "Open Water",
            "Barren",
            "Shrubland",
            "Evergreen Forest",
            "Deciduous Forest",
            "Mixed Forest",
            "Woody Wetlands",
            "Herbaceous Wetlands",
        }
        for site in self.manifest["sites"]:
            verification = site["coordinate_verification"]
            self.assertEqual(verification["status"], "verified_usda_cdl_2024")
            self.assertEqual(verification["source_id"], "USDA_NASS_CDL_2024")
            self.assertEqual(verification["dataset_year"], 2024)
            self.assertEqual(verification["resolution_m"], 10)
            self.assertNotIn(verification["class_name"], disallowed_classes, site["site_id"])

    def test_only_el_paso_site_uses_mountain_time(self):
        mountain_sites = [
            site["site_id"]
            for site in self.manifest["sites"]
            if site["timezone"] == "America/Denver"
        ]
        self.assertEqual(mountain_sites, ["far_west_el_paso_lower_valley_fabens"])

    def test_points_are_representatives_not_claimed_boundaries(self):
        limitation = self.manifest["selection_policy"]["limitation"].lower()
        self.assertIn("representative", limitation)
        self.assertIn("not farm parcels", limitation)
        for site in self.manifest["sites"]:
            warning = site["coordinate_verification"]["warning"].lower()
            self.assertTrue(
                "not" in warning or "does not" in warning,
                site["site_id"],
            )


if __name__ == "__main__":
    unittest.main()
