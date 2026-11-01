"""Check physical calculations, feasibility boundaries, and global scheduling."""

from copy import deepcopy
import unittest

from main import sample_scenario
from src.ev_scheduler import calculate_journey, generate_options, solve_exact, validate_scenario


def small_scenario():
    """One car needs exactly 10 kWh: 50 * (40% - 20%)."""
    return {
        "vehicles": [{
            "id": "A", "battery_capacity_kwh": 50,
            "current_charge_percent": 20, "target_charge_percent": 40,
            "consumption_kwh_per_km": 0.2,
            "available_from_minute": 480, "deadline_minute": 540,
        }],
        "stations": [{"id": "North", "power_kw": 10, "prices_per_kwh": {"early": 2}}],
        "slots": [{"id": "early", "start_minute": 480, "end_minute": 540}],
        "travel": {"A": {"North": {"distance_km": 0, "duration_minutes": 0}}},
    }


class OptionGenerationTests(unittest.TestCase):
    def test_journey_and_option_arithmetic(self):
        scenario = small_scenario()
        vehicle = scenario["vehicles"][0]
        vehicle["available_from_minute"] = 460
        vehicle["deadline_minute"] = 600
        scenario["stations"][0]["power_kw"] = 22
        scenario["travel"]["A"]["North"] = {"distance_km": 5, "duration_minutes": 15}

        journey = calculate_journey(vehicle, scenario["travel"]["A"]["North"])
        # 10 initial - (5 km * 0.2 kWh/km) = 9 at arrival; target is 20.
        self.assertAlmostEqual(journey["initial_energy_kwh"], 10)
        self.assertAlmostEqual(journey["driving_energy_kwh"], 1)
        self.assertAlmostEqual(journey["arrival_energy_kwh"], 9)
        self.assertEqual(journey["arrival_minute"], 475)
        self.assertAlmostEqual(journey["charging_energy_kwh"], 11)

        booking = generate_options(scenario)["options"]["A"][0]
        self.assertAlmostEqual(booking["charging_duration_minutes"], 30)
        self.assertAlmostEqual(booking["completion_minute"], 510)
        self.assertEqual(booking["waiting_minutes"], 5)
        self.assertAlmostEqual(booking["electricity_cost_rupees"], 22)
        self.assertAlmostEqual(booking["score"], 23.25)

    def test_arrival_slot_capacity_and_deadline_exact_boundaries(self):
        generated = generate_options(small_scenario())
        self.assertEqual(generated["rejected"], [])
        booking = generated["options"]["A"][0]
        self.assertEqual(booking["arrival_minute"], 480)
        self.assertEqual(booking["waiting_minutes"], 0)
        self.assertAlmostEqual(booking["completion_minute"], 540)
        self.assertAlmostEqual(booking["charging_energy_kwh"], 10)

    def test_charging_may_finish_before_reserved_slot_ends(self):
        scenario = small_scenario()
        scenario["stations"][0]["power_kw"] = 20
        scenario["vehicles"][0]["deadline_minute"] = 510
        booking = generate_options(scenario)["options"]["A"][0]
        self.assertAlmostEqual(booking["completion_minute"], 510)
        self.assertEqual(booking["end_minute"], 540)

    def test_arrival_exactly_at_reserve_is_allowed(self):
        scenario = small_scenario()
        scenario["vehicles"][0]["current_charge_percent"] = 5
        scenario["vehicles"][0]["target_charge_percent"] = 25
        self.assertEqual(len(generate_options(scenario)["options"]["A"]), 1)

    def test_each_rejection_rule(self):
        cases = [
            ("reserve", "below the required reserve"),
            ("arrival", "Arrival is after"),
            ("deadline", "after the vehicle deadline"),
            ("power", "cannot deliver"),
        ]
        for change, expected_reason in cases:
            with self.subTest(change=change):
                scenario = small_scenario()
                if change == "reserve":
                    scenario["vehicles"][0]["current_charge_percent"] = 4
                elif change == "arrival":
                    scenario["travel"]["A"]["North"]["duration_minutes"] = 1
                elif change == "deadline":
                    scenario["vehicles"][0]["deadline_minute"] = 539
                else:
                    scenario["stations"][0]["power_kw"] = 9
                generated = generate_options(scenario)
                self.assertEqual(generated["options"]["A"], [])
                self.assertTrue(any(expected_reason in reason for reason in generated["rejected"][0]["reasons"]))

    def test_multiple_rejection_reasons_are_preserved(self):
        rejected = generate_options(sample_scenario())["rejected"]
        south_early = next(r for r in rejected if r["station_id"] == "South" and r["slot_id"] == "early")
        self.assertEqual(len(south_early["reasons"]), 4)

    def test_scenario_is_not_mutated(self):
        scenario = sample_scenario()
        original = deepcopy(scenario)
        generated = generate_options(scenario)
        original_options = deepcopy(generated["options"])
        solve_exact(scenario, generated["options"])
        self.assertEqual(scenario, original)
        self.assertEqual(generated["options"], original_options)

    def test_free_electricity_and_zero_waiting_weight(self):
        scenario = small_scenario()
        scenario["stations"][0]["prices_per_kwh"]["early"] = 0
        scenario["waiting_weight_per_minute"] = 0
        booking = generate_options(scenario)["options"]["A"][0]
        self.assertEqual(booking["score"], 0)


class ExactSolverTests(unittest.TestCase):
    def test_hand_calculated_single_car_optimum(self):
        scenario = small_scenario()
        result = solve_exact(scenario, generate_options(scenario)["options"])
        self.assertEqual(result["status"], "optimal")
        self.assertAlmostEqual(result["total_electricity_cost_rupees"], 20)
        self.assertEqual(result["total_waiting_minutes"], 0)
        self.assertAlmostEqual(result["total_score"], 20)
        self.assertEqual(result["combinations_checked"], 1)

    def test_demo_optimum_and_greedy_failure(self):
        scenario = sample_scenario()
        options = generate_options(scenario)["options"]
        cheapest_a = min(options["A"], key=lambda booking: booking["score"])
        only_b = options["B"][0]
        self.assertEqual((cheapest_a["station_id"], cheapest_a["slot_id"]),
                         (only_b["station_id"], only_b["slot_id"]))

        result = solve_exact(scenario, options)
        assignments = [(b["vehicle_id"], b["station_id"], b["slot_id"]) for b in result["schedule"]]
        self.assertEqual(assignments, [("A", "North", "late"), ("B", "North", "early")])
        # Independent arithmetic: bill = 10.4*1 + 9.2*2; wait = 65+5.
        self.assertAlmostEqual(result["total_electricity_cost_rupees"], 28.8)
        self.assertEqual(result["total_waiting_minutes"], 70)
        self.assertAlmostEqual(result["total_score"], 46.3)
        self.assertEqual(result["combinations_checked"], 4)
        self.assertEqual(result["feasible_combinations"], 3)

    def test_no_individually_feasible_booking(self):
        scenario = small_scenario()
        scenario["stations"][0]["power_kw"] = 1
        result = solve_exact(scenario, generate_options(scenario)["options"])
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("No feasible booking for: A", result["reason"])
        self.assertEqual(result["combinations_checked"], 0)
        self.assertEqual(result["schedule"], [])
        self.assertIsNone(result["total_score"])

    def test_individual_options_exist_but_no_global_schedule(self):
        scenario = small_scenario()
        car_b = {**scenario["vehicles"][0], "id": "B"}
        scenario["vehicles"].append(car_b)
        scenario["travel"]["B"] = deepcopy(scenario["travel"]["A"])
        options = generate_options(scenario)["options"]
        self.assertTrue(options["A"] and options["B"])
        result = solve_exact(scenario, options)
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("conflict", result["reason"])
        self.assertEqual(result["combinations_checked"], 1)
        self.assertEqual(result["feasible_combinations"], 0)

    def test_equal_scores_keep_station_input_order(self):
        scenario = small_scenario()
        scenario["stations"].append({**scenario["stations"][0], "id": "South"})
        scenario["travel"]["A"]["South"] = deepcopy(scenario["travel"]["A"]["North"])
        result = solve_exact(scenario, generate_options(scenario)["options"])
        self.assertEqual(result["schedule"][0]["station_id"], "North")
        scenario["stations"].reverse()
        result = solve_exact(scenario, generate_options(scenario)["options"])
        self.assertEqual(result["schedule"][0]["station_id"], "South")

    def test_changed_waiting_preference_changes_the_schedule(self):
        scenario = sample_scenario()
        scenario["waiting_weight_per_minute"] = 1
        result = solve_exact(scenario, generate_options(scenario)["options"])
        assignments = [(b["vehicle_id"], b["station_id"], b["slot_id"]) for b in result["schedule"]]
        self.assertEqual(assignments, [("A", "South", "early"), ("B", "North", "early")])
        self.assertEqual(result["total_waiting_minutes"], 5)
        self.assertAlmostEqual(result["total_electricity_cost_rupees"], 51.4)
        self.assertAlmostEqual(result["total_score"], 56.4)

    def test_full_slot_stays_reserved_after_early_completion(self):
        scenario = small_scenario()
        scenario["stations"][0]["power_kw"] = 20
        scenario["vehicles"].append({**scenario["vehicles"][0], "id": "B"})
        scenario["travel"]["B"] = deepcopy(scenario["travel"]["A"])
        result = solve_exact(scenario, generate_options(scenario)["options"])
        self.assertEqual(result["status"], "infeasible")


class InputValidationTests(unittest.TestCase):
    def test_duplicate_ids(self):
        for collection in ("vehicles", "stations", "slots"):
            with self.subTest(collection=collection):
                scenario = small_scenario()
                scenario[collection].append(deepcopy(scenario[collection][0]))
                with self.assertRaisesRegex(ValueError, "duplicate ID"):
                    validate_scenario(scenario)

    def test_invalid_numbers_and_windows(self):
        cases = [
            ("vehicle", "battery_capacity_kwh", 0),
            ("vehicle", "consumption_kwh_per_km", -1),
            ("vehicle", "current_charge_percent", -1),
            ("vehicle", "target_charge_percent", 101),
            ("vehicle", "target_charge_percent", 20),
            ("vehicle", "available_from_minute", 540),
            ("vehicle", "available_from_minute", 480.5),
            ("vehicle", "deadline_minute", 1500),
            ("station", "power_kw", 0),
            ("station", "power_kw", float("nan")),
            ("station", "power_kw", float("inf")),
            ("station", "power_kw", True),
            ("price", "early", -1),
            ("slot", "end_minute", 539),
            ("travel", "distance_km", -1),
            ("travel", "duration_minutes", -1),
            ("scenario", "reserve_percent", 101),
            ("scenario", "waiting_weight_per_minute", -1),
        ]
        for section, field, value in cases:
            with self.subTest(section=section, field=field, value=value):
                scenario = small_scenario()
                locations = {
                    "vehicle": scenario["vehicles"][0], "station": scenario["stations"][0],
                    "price": scenario["stations"][0]["prices_per_kwh"],
                    "slot": scenario["slots"][0], "travel": scenario["travel"]["A"]["North"],
                    "scenario": scenario,
                }
                locations[section][field] = value
                with self.assertRaises(ValueError):
                    validate_scenario(scenario)

    def test_missing_travel_or_price(self):
        for missing in ("vehicle", "station", "distance", "price"):
            with self.subTest(missing=missing):
                scenario = small_scenario()
                if missing == "vehicle":
                    del scenario["travel"]["A"]
                elif missing == "station":
                    del scenario["travel"]["A"]["North"]
                elif missing == "distance":
                    del scenario["travel"]["A"]["North"]["distance_km"]
                else:
                    del scenario["stations"][0]["prices_per_kwh"]["early"]
                with self.assertRaises(ValueError):
                    validate_scenario(scenario)

    def test_overlapping_slots(self):
        scenario = small_scenario()
        scenario["slots"].append({"id": "overlap", "start_minute": 510, "end_minute": 570})
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_scenario(scenario)

    def test_malformed_inputs_fail_with_value_error(self):
        for scenario in (None, {}, {**small_scenario(), "vehicles": []}):
            with self.subTest(scenario=scenario):
                with self.assertRaises(ValueError):
                    validate_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
