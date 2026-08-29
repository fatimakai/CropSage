import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from providers.common import FetchOutcome, LocationTarget, manifest_target
from providers.fortyguard import fetch_fortyguard
from providers.nasa_power import (
    ADDITIONAL_PARAMETERS,
    ALL_PARAMETERS,
    PRIMARY_PARAMETERS,
    fetch_nasa_power,
)
from providers.open_meteo import (
    CURRENT_VARIABLES,
    DAILY_VARIABLES,
    HOURLY_VARIABLES,
    fetch_open_meteo,
)
from providers.ssurgo import fetch_ssurgo
from scripts.collect_location_evidence import collect_location


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload, url="https://example.test", status_code=200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = str(payload)

    def json(self):
        return self._payload


class ProviderCollectionTests(unittest.TestCase):
    def setUp(self):
        self.location = LocationTarget(
            farm_id="poteet_test",
            farm_name="Poteet test farm",
            latitude=28.89,
            longitude=-98.60,
            texas_region_id="central_south_winter_garden",
            timezone="America/Chicago",
        )

    def test_manifest_location_is_ready_for_generic_collection(self):
        site = manifest_target("central_south_poteet")
        self.assertEqual(site.texas_region_id, "central_south_winter_garden")
        self.assertAlmostEqual(site.latitude, 28.89)
        self.assertAlmostEqual(site.longitude, -98.60)

    def test_nasa_power_normalizes_climatology_and_daily_history(self):
        class Session:
            def get(inner_self, _url, params, timeout):
                requested = tuple(params["parameters"].split(","))
                if "start" in params:
                    values = {
                        parameter: {"20250101": 20.0 + index}
                        for index, parameter in enumerate(ALL_PARAMETERS)
                    }
                    return FakeResponse(
                        {
                            "geometry": {"type": "Point", "coordinates": [-98.6, 28.89, 100]},
                            "properties": {"parameter": values},
                        },
                        "https://power.test/daily",
                    )
                values = {
                    parameter: {period: 10.0 for period in ("JAN", "ANN")}
                    for parameter in requested
                }
                return FakeResponse(
                    {
                        "properties": {"parameter": values},
                        "parameters": {
                            parameter: {"longname": parameter, "units": "test"}
                            for parameter in requested
                        },
                    },
                    "https://power.test/climatology",
                )

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "nasa_power.json"
            outcome = fetch_nasa_power(
                self.location,
                output_path=output,
                history_year=2025,
                session=Session(),
                now=NOW,
            )
        self.assertEqual(outcome.artifact["quality"]["returned_parameter_count"], 11)
        history = outcome.artifact["daily_history_2025"]
        self.assertEqual(history["daily_records"][0]["date"], "2025-01-01")
        self.assertIsNotNone(history["daily_records"][0]["VPD_KPA"])
        self.assertEqual(len(history["monthly_summary"]), 12)
        self.assertEqual(set(PRIMARY_PARAMETERS + ADDITIONAL_PARAMETERS), set(ALL_PARAMETERS))

    def test_open_meteo_splits_recent_and_forecast_and_counts_zero_as_frost(self):
        dates = [f"2026-08-{day:02d}" for day in range(1, 15)]
        daily = {"time": dates}
        for field in DAILY_VARIABLES:
            daily[field] = [1.0] * 14
        daily["temperature_2m_max"] = [30.0] * 7 + [34.0, 35.0, 36.0, 30.0, 30.0, 30.0, 30.0]
        daily["temperature_2m_min"] = [10.0] * 7 + [0.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        current = {field: 1.0 for field in CURRENT_VARIABLES}
        current["time"] = "2026-08-08T12:00"
        hourly = {"time": ["2026-08-08T12:00", "2026-08-08T13:00"]}
        for field in HOURLY_VARIABLES:
            hourly[field] = [1.0, 1.0]
        payload = {
            "latitude": 28.9,
            "longitude": -98.6,
            "timezone": "America/Chicago",
            "current": current,
            "current_units": {field: "test" for field in CURRENT_VARIABLES},
            "daily": daily,
            "daily_units": {field: "test" for field in DAILY_VARIABLES},
            "hourly": hourly,
            "hourly_units": {field: "test" for field in HOURLY_VARIABLES},
        }

        class Session:
            def get(inner_self, _url, params, timeout):
                return FakeResponse(payload, "https://open-meteo.test/forecast")

        with tempfile.TemporaryDirectory() as folder:
            outcome = fetch_open_meteo(
                self.location,
                output_path=Path(folder) / "open_meteo.json",
                session=Session(),
                now=NOW,
            )
        artifact = outcome.artifact
        self.assertEqual(len(artifact["recent_complete_days"]["records"]), 7)
        self.assertEqual(len(artifact["forecast"]["daily_records"]), 7)
        summary = artifact["forecast"]["operational_summary"]
        self.assertEqual(summary["forecast_frost_risk_days_at_or_below_0c"], 1.0)
        self.assertEqual(summary["forecast_heat_days_at_or_above_35c"], 2.0)

    def test_ssurgo_builds_soil_summary_and_all_crop_comparisons(self):
        headers = [
            "areasymbol", "saverest", "mukey", "musym", "muname", "farmlndcl",
            "cokey", "compname", "comppct_r", "majcompflag", "drainagecl",
            "hydricrating", "restrictive_depth_cm", "chkey", "hzname", "hzdept_r",
            "hzdepb_r", "awc_r", "ph1to1h2o_r", "sandtotal_r", "silttotal_r",
            "claytotal_r", "texture",
        ]
        base = [
            "TX001", "2025-01-01", "1", "Aa", "Test loam", "Prime farmland",
            "10", "Test component", 80, "Yes", "Well drained", "No", None,
        ]
        rows = [
            base + ["100", "A", 0, 30, 0.18, 6.5, 40, 40, 20, "FSL"],
            base + ["101", "B", 30, 150, 0.15, 6.8, 35, 40, 25, "CL"],
        ]

        class Session:
            def post(inner_self, _url, json, timeout):
                return FakeResponse({"Table": [headers, *rows]})

        with tempfile.TemporaryDirectory() as folder:
            outcome = fetch_ssurgo(
                self.location,
                output_path=Path(folder) / "ssurgo.json",
                session=Session(),
                now=NOW,
            )
        self.assertEqual(
            outcome.artifact["soil_summary"]["surface_texture"], "fine sandy loam"
        )
        self.assertEqual(outcome.artifact["soil_summary"]["mapped_ph_0_30cm"], 6.5)
        self.assertEqual(len(outcome.artifact["crop_comparisons"]), 22)

    def test_fortyguard_uses_filter_four_and_only_six_scoreable_thresholds(self):
        class Client:
            def __init__(inner_self):
                inner_self.payloads = []

            def submit_heatmap(inner_self, payload):
                inner_self.payloads.append(payload)
                return f"activity-{len(inner_self.payloads)}"

            def wait_for(inner_self, activity_id, *, poll_interval, timeout):
                payload = inner_self.payloads[int(activity_id.split("-")[-1]) - 1]
                analytic = payload["analytic_type"]
                if analytic == "tcm":
                    values = [29.0, 31.0]
                    features = [
                        {
                            "properties": {
                                "tile_id": index,
                                "average_temperature": value,
                                "min_temperature": 19.0 + index,
                                "max_temperature": 39.0 + index,
                            }
                        }
                        for index, value in enumerate(values)
                    ]
                    stats = {
                        "temperature_stats": {"minimum": 20.0, "maximum": 40.0, "mean": 30.0}
                    }
                else:
                    value = 4.0 if analytic == "exceedance" else 2.0
                    features = [
                        {"properties": {"tile_id": index, "value": value}}
                        for index in range(2)
                    ]
                    stats = {"analytic_type": analytic, "units": "hour"}
                return {"map_data": {"features": features}, "stats_data": stats}

        client = Client()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fortyguard.json"
            first = fetch_fortyguard(
                self.location,
                output_path=output,
                client=client,
                end_date=date(2026, 8, 25),
                now=NOW,
            )
            second = fetch_fortyguard(
                self.location,
                output_path=output,
                client=client,
                end_date=date(2026, 8, 25),
                now=NOW,
            )
        self.assertEqual(len(client.payloads), 13)
        self.assertTrue(all(p["date_time"]["filter_type"] == 4 for p in client.payloads))
        thresholds = sorted({p["threshold"] for p in client.payloads if "threshold" in p})
        self.assertEqual(thresholds, [27.8, 29.4, 30.0, 35.0, 37.2, 37.8])
        self.assertEqual(len(first.artifact["tests"]["test_one_week"]["crop_results"]), 22)
        self.assertEqual(first.artifact["validation"]["total_validated_responses"], 13)
        summary = first.artifact["period_comparison"][0]
        self.assertEqual(summary["minimum_tile_average_temperature_c"], 29.0)
        self.assertEqual(summary["maximum_tile_average_temperature_c"], 31.0)
        self.assertEqual(summary["period_minimum_temperature_c"], 19.0)
        self.assertEqual(summary["period_maximum_temperature_c"], 40.0)
        self.assertNotIn("minimum_temperature_c", summary)
        self.assertNotIn("maximum_temperature_c", summary)
        self.assertEqual(second.cache_state, "fresh_cache")

    def test_fortyguard_timeout_resumes_the_same_activity(self):
        class Client:
            def __init__(inner_self):
                inner_self.payloads = []
                inner_self.fail_first_wait = True

            def submit_heatmap(inner_self, payload):
                inner_self.payloads.append(payload)
                return f"activity-{len(inner_self.payloads)}"

            def wait_for(inner_self, activity_id, *, poll_interval, timeout):
                if inner_self.fail_first_wait:
                    inner_self.fail_first_wait = False
                    raise RuntimeError("simulated local polling timeout")
                payload = inner_self.payloads[int(activity_id.split("-")[-1]) - 1]
                analytic = payload["analytic_type"]
                if analytic == "tcm":
                    return {
                        "map_data": {"features": [
                            {"properties": {
                                "tile_id": 1,
                                "average_temperature": 30.0,
                                "min_temperature": 25.0,
                                "max_temperature": 38.0,
                            }}
                        ]},
                        "stats_data": {"temperature_stats": {"minimum": 25.0, "maximum": 38.0}},
                    }
                return {
                    "map_data": {"features": [{"properties": {"tile_id": 1, "value": 1.0}}]},
                    "stats_data": {"analytic_type": analytic, "units": "hour"},
                }

        client = Client()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fortyguard.json"
            with self.assertRaisesRegex(RuntimeError, "simulated local polling timeout"):
                fetch_fortyguard(
                    self.location,
                    output_path=output,
                    client=client,
                    end_date=date(2026, 8, 25),
                    now=NOW,
                )
            fetch_fortyguard(
                self.location,
                output_path=output,
                client=client,
                end_date=date(2026, 8, 25),
                now=NOW,
            )
        self.assertEqual(len(client.payloads), 13)
        self.assertEqual(client.payloads[0]["analytic_type"], "tcm")

    def test_orchestrator_calls_all_four_adapters_and_keeps_contract_paths(self):
        calls = []

        def fake(name):
            def run(_location, *, output_path, **kwargs):
                calls.append((name, output_path.name, kwargs))
                return FetchOutcome(name, {"provider": name}, output_path, "fake")
            return run

        functions = {name: fake(name) for name in ("nasa_power", "open_meteo", "ssurgo", "fortyguard")}
        with tempfile.TemporaryDirectory() as folder:
            result = collect_location(
                self.location,
                output_directory=Path(folder),
                build_bundle=False,
                parallel=False,
                provider_functions=functions,
            )
        self.assertEqual(set(result.providers), set(functions))
        self.assertEqual(
            {filename for _, filename, _ in calls},
            {"nasa_power.json", "open_meteo.json", "ssurgo.json", "fortyguard.json"},
        )


if __name__ == "__main__":
    unittest.main()
