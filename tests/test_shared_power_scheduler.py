"""Physical validation, exhaustive QUBO checks, and shared-power QAOA integration."""

from copy import deepcopy
from itertools import product
import unittest

from shared_power_demo import sample_shared_power_scenario
from src.shared_power_scheduler import (
    build_shared_power_qubo, decode_shared_power_bits, generate_shared_power_options,
    solve_shared_power_exact, validate_shared_power_scenario,
)
from src.quantum_scheduler import qubo_to_ising, qubo_value, solve_qaoa, summarize_counts


def select(model, *choices):
    """choices = (vehicle, gun, power profile, module) tuples."""
    bits = [0] * len(model["variables"])
    for vehicle_id, gun, profile, module_id in choices:
        index = next(i for i, p in enumerate(model["variables"])
                     if (p["vehicle_id"], p["gun"], p["power_kw_by_slot"], p["module_id"])
                     == (vehicle_id, gun, profile, module_id))
        bits[index] = 1
    return bits


class SharedPowerEncodingTests(unittest.TestCase):
    def setUp(self):
        self.scenario = sample_shared_power_scenario()
        self.model = build_shared_power_qubo(self.scenario)

    def test_profiles_include_both_power_allocations_and_exact_energy(self):
        self.assertEqual(len(self.model["variables"]), 8)
        for p in self.model["variables"]:
            self.assertAlmostEqual(sum(p["power_kw_by_slot"]) * 0.5, p["charging_energy_kwh"])
        a_profiles = {p["power_kw_by_slot"] for p in self.model["variables"] if p["vehicle_id"] == "A"}
        self.assertEqual(a_profiles, {(25, 50), (50, 25)})

    def test_grid_alignment_uses_the_same_kwh_tolerance_as_decoding(self):
        self.scenario["vehicles"][0]["required_energy_kwh"] = 37.5000001
        with self.assertRaisesRegex(ValueError, "multiple"):
            build_shared_power_qubo(self.scenario)
        self.scenario["vehicles"][0]["required_energy_kwh"] = 37.500000001
        model = build_shared_power_qubo(self.scenario)
        self.assertEqual(solve_shared_power_exact(model)["status"], "optimal")

    def test_power_rounding_respects_physical_kw_tolerance(self):
        self.scenario["vehicles"][1]["max_power_kw"] = 24.9999999
        self.assertEqual(generate_shared_power_options(self.scenario)["B"], [])
        self.scenario["vehicles"][1]["max_power_kw"] = 24.999999999
        self.assertEqual(solve_shared_power_exact(build_shared_power_qubo(self.scenario))["status"], "optimal")
        self.scenario["modules"][0]["power_kw"] = 24.9999999
        self.assertTrue(all(not plans for plans in generate_shared_power_options(self.scenario).values()))

    def test_long_horizons_obey_candidate_budget_without_recursion_error(self):
        self.scenario.update(num_slots=1440, slot_minutes=1)
        for vehicle in self.scenario["vehicles"]:
            vehicle["deadline_minute"] = 1440
        with self.assertRaisesRegex(ValueError, "Too many candidate"):
            generate_shared_power_options(self.scenario, max_options_per_vehicle=1)

    def test_25_plus_25_then_50_plus_zero_is_valid_and_optimal(self):
        bits = select(self.model, ("A", 0, (25, 50), "M1"), ("B", 1, (25, 0), "M1"))
        self.assertTrue(decode_shared_power_bits(self.model, bits)["valid"])
        self.assertAlmostEqual(qubo_value(self.model, bits), 90)
        reference = solve_shared_power_exact(self.model)
        self.assertEqual(reference["status"], "optimal")
        self.assertEqual(reference["total_flow_minutes"], 90)
        self.assertEqual(reference["average_flow_minutes"], 45)
        self.assertEqual(reference["last_completion_minute"], 60)

    def test_vehicle_limits_alone_do_not_allow_50_plus_25(self):
        bits = select(self.model, ("A", 0, (50, 25), "M1"), ("B", 1, (25, 0), "M1"))
        decoded = decode_shared_power_bits(self.model, bits)
        self.assertFalse(decoded["valid"])
        self.assertTrue(any("Shared power exceeded" in reason for reason in decoded["reasons"]))
        self.assertGreater(qubo_value(self.model, bits), self.model["score_bound"])

    def test_same_gun_conflict_is_rejected_even_with_sufficient_power(self):
        bits = select(self.model, ("A", 0, (25, 50), "M1"), ("B", 0, (25, 0), "M1"))
        reasons = decode_shared_power_bits(self.model, bits)["reasons"]
        self.assertTrue(any("Gun conflict" in reason for reason in reasons))

    def test_every_bitstring_agrees_with_independent_physical_checks(self):
        valid_scores, invalid_scores = [], []
        # Do not reuse the model's precomputed conflict list to check physics.
        plans, penalty = self.model["variables"], self.model["penalty"]
        for bits in product((0, 1), repeat=8):
            selected = [p for p, bit in zip(plans, bits) if bit]
            count_penalty = sum((sum(p["vehicle_id"] == v for p in selected) - 1)**2 for v in ("A", "B"))
            pair_penalty = 0
            for i, first in enumerate(selected):
                for second in selected[i + 1:]:
                    if first["vehicle_id"] == second["vehicle_id"]:
                        continue
                    gun_overlap = first["gun"] == second["gun"] and any(
                        first["start_slot"] <= t < first["end_slot"]
                        and second["start_slot"] <= t < second["end_slot"] for t in range(2))
                    overload = any(first["power_kw_by_slot"][t] + second["power_kw_by_slot"][t] > 50 for t in range(2))
                    pair_penalty += gun_overlap or overload
            expected = sum(p["score"] for p in selected) + penalty * (count_penalty + pair_penalty)
            energy = qubo_value(self.model, bits)
            self.assertAlmostEqual(energy, expected)
            valid = decode_shared_power_bits(self.model, bits)["valid"]
            self.assertEqual(valid, count_penalty == pair_penalty == 0)
            (valid_scores if valid else invalid_scores).append(energy)
        self.assertEqual(min(valid_scores), 90)
        self.assertLess(max(valid_scores), min(invalid_scores))

    def test_ising_energies_match_all_256_binary_assignments(self):
        ising = qubo_to_ising(self.model)
        diagonal = ising["operator"].to_matrix().diagonal()
        for bits in product((0, 1), repeat=8):
            index = sum(bit << i for i, bit in enumerate(bits))
            self.assertAlmostEqual(diagonal[index].real + ising["offset"], qubo_value(self.model, bits))

    def test_multiple_modules_have_independent_budgets(self):
        self.scenario["modules"].append({"id": "M2", "power_kw": 50})
        model = build_shared_power_qubo(self.scenario)
        bits = select(model, ("A", 0, (50, 25), "M1"), ("B", 0, (25, 0), "M2"))
        self.assertTrue(decode_shared_power_bits(model, bits)["valid"])

    def test_deadline_horizon_arrival_and_late_gun_reuse(self):
        scenario = sample_shared_power_scenario()
        scenario["vehicles"][0]["required_energy_kwh"] = 12.5
        scenario["vehicles"][0]["max_power_kw"] = 25
        scenario["vehicles"][1]["arrival_minute"] = 1
        model = build_shared_power_qubo(scenario)
        bits = select(model, ("A", 0, (25, 0), "M1"), ("B", 0, (0, 25), "M1"))
        self.assertTrue(decode_shared_power_bits(model, bits)["valid"])
        result = solve_shared_power_exact(model)
        self.assertEqual(result["total_flow_minutes"], 89)
        self.assertEqual(result["total_waiting_minutes"], 29)
        scenario["vehicles"][1]["deadline_minute"] = 59
        self.assertEqual(generate_shared_power_options(scenario)["B"], [])

    def test_paused_car_keeps_its_gun(self):
        self.scenario["num_slots"] = 3
        for vehicle in self.scenario["vehicles"]:
            vehicle["deadline_minute"] = 90
        self.scenario["vehicles"][0]["required_energy_kwh"] = 25
        model = build_shared_power_qubo(self.scenario)
        bits = select(model, ("A", 0, (25, 0, 25), "M1"), ("B", 0, (0, 25, 0), "M1"))
        self.assertFalse(decode_shared_power_bits(model, bits)["valid"])

    def test_individual_options_can_exist_without_joint_feasibility(self):
        self.scenario["vehicles"][1]["required_energy_kwh"] = 25
        model = build_shared_power_qubo(self.scenario)
        self.assertTrue(all(model["groups"].values()))
        self.assertEqual(solve_shared_power_exact(model)["status"], "infeasible")

    def test_input_is_not_mutated_and_is_snapshotted(self):
        original = deepcopy(self.scenario)
        model = build_shared_power_qubo(self.scenario)
        self.assertEqual(self.scenario, original)
        self.scenario["modules"][0]["power_kw"] = 1
        self.assertEqual(model["scenario"], original)

    def test_three_cars_cannot_bypass_the_two_gun_limit(self):
        scenario = sample_shared_power_scenario()
        scenario["num_slots"] = 1
        scenario["vehicles"] = [
            {"id": name, "required_energy_kwh": 12.5, "max_power_kw": 25,
             "arrival_minute": 0, "deadline_minute": 30} for name in ("A", "B", "C")
        ]
        model = build_shared_power_qubo(scenario)
        # Every pair would fit the 50 kW budget, but three simultaneous cars
        # must share a gun. The pairwise gun edges enforce this constraint.
        self.assertEqual(solve_shared_power_exact(model)["status"], "infeasible")

    def test_four_cars_can_share_two_independent_modules(self):
        scenario = sample_shared_power_scenario()
        scenario["num_slots"] = 1
        scenario["modules"].append({"id": "M2", "power_kw": 50})
        scenario["vehicles"] = [
            {"id": name, "required_energy_kwh": 12.5, "max_power_kw": 25,
             "arrival_minute": 0, "deadline_minute": 30} for name in ("A", "B", "C", "D")
        ]
        model = build_shared_power_qubo(scenario)
        result = solve_shared_power_exact(model)
        self.assertEqual(result["status"], "optimal")
        self.assertEqual(result["average_flow_minutes"], 30)
        self.assertEqual({p["module_id"] for p in result["schedule"]}, {"M1", "M2"})

    def test_bad_grid_and_unsupported_capacity_assumptions(self):
        for key, value, message in (
            ("energy", 1, "multiple"), ("guns", 3, "two guns"),
            ("site", 25, "aggregate-capacity"), ("power", True, "finite number"),
            ("slots", 0, "positive integer"), ("deadline", 0, "arrival must precede"),
        ):
            with self.subTest(key=key):
                scenario = deepcopy(self.scenario)
                if key == "energy":
                    scenario["vehicles"][0]["required_energy_kwh"] = value
                elif key == "guns":
                    scenario["modules"][0]["gun_count"] = value
                elif key == "site":
                    scenario["site_power_kw"] = value
                elif key == "power":
                    scenario["power_step_kw"] = value
                elif key == "slots":
                    scenario["num_slots"] = value
                else:
                    scenario["vehicles"][0]["deadline_minute"] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_shared_power_scenario(scenario)
        with self.assertRaisesRegex(ValueError, "safe score bound"):
            build_shared_power_qubo(self.scenario, penalty=1)
        with self.assertRaisesRegex(ValueError, "Too many candidate"):
            build_shared_power_qubo(self.scenario, max_options_per_vehicle=1)
        with self.assertRaisesRegex(ValueError, "Exact reference needs"):
            solve_shared_power_exact(self.model, max_combinations=1)
        self.scenario["vehicles"][0]["deadline_minute"] = 30
        with self.assertRaisesRegex(ValueError, "No grid-feasible"):
            build_shared_power_qubo(self.scenario)


class SharedPowerQuantumTests(unittest.TestCase):
    def setUp(self):
        self.model = build_shared_power_qubo(sample_shared_power_scenario())

    def test_measured_counts_decode_time_objective_without_inventing_tariffs(self):
        bits = select(self.model, ("A", 0, (25, 50), "M1"), ("B", 1, (25, 0), "M1"))
        string = "".join(str(bit) for bit in reversed(bits))
        result = summarize_counts(self.model, {string: 3, "00000000": 1})
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["total_score"], 90)
        self.assertEqual(result["average_flow_minutes"], 45)
        self.assertIsNone(result["total_electricity_cost_rupees"])
        self.assertEqual(result["valid_sample_fraction"], 0.75)
        invalid = summarize_counts(self.model, {"00000000": 1})
        self.assertEqual(invalid["status"], "no_feasible_sample")
        self.assertIsNone(invalid["total_flow_minutes"])

    def test_actual_qaoa_runs_the_shared_model_and_selects_only_measured_valid_plans(self):
        result = solve_qaoa(self.model, layers=1, iterations=24, restarts=1, shots=1024, seed=7)
        self.assertEqual(sum(result["counts"].values()), 1024)
        self.assertEqual(result["status"], "feasible")
        self.assertTrue(decode_shared_power_bits(self.model, result["bits"])["valid"])
        self.assertIn("".join(map(str, reversed(result["bits"]))), result["counts"])
        measured = [s["qubo_score"] for s in result["samples"] if s["valid"]]
        self.assertAlmostEqual(result["total_score"], min(measured))

    def test_simulation_size_is_checked_before_allocating_statevector(self):
        with self.assertRaisesRegex(ValueError, "local simulation limit"):
            solve_qaoa(self.model, max_qubits=7)


if __name__ == "__main__":
    unittest.main()
