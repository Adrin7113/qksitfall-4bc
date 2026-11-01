"""Independent baselines, report integrity and the unchanged QAOA benchmark."""

from copy import deepcopy
from itertools import product
import unittest

import numpy as np

from src.quantum_benchmark import (
    analyze_counts, benchmark_cases, candidate_view, fingerprint,
    native_milp_constraints, run_benchmark, run_trial, summarize_runs,
    validate_report, validate_selection,
)
from src.shared_power_scheduler import build_shared_power_qubo, solve_shared_power_exact


class BenchmarkTests(unittest.TestCase):
    def test_five_cases_match_approved_sizes_and_reference_optima(self):
        cases = benchmark_cases()
        for case, qubits, optimum in zip(cases, [8, 6, 6, 12, 8], [90, 90, 90, 120, 60]):
            model = build_shared_power_qubo(case["scenario"])
            view = candidate_view(case["scenario"])
            self.assertEqual(len(model["variables"]), qubits)
            self.assertEqual(fingerprint(view["variables"]), fingerprint(model["variables"]))
            self.assertEqual(solve_shared_power_exact(model)["total_score"], optimum)
            result = run_trial(case["scenario"], "milp", 0, optimum)
            self.assertEqual(result["status"], "feasible")
            self.assertEqual(result["best_total_flow_minutes"], optimum)
            self.assertIsNone(result["feasible_sample_fraction"])

    def test_native_linear_constraints_match_physics_for_all_original_bitstrings(self):
        scenario = benchmark_cases()[0]["scenario"]
        view = candidate_view(scenario)
        constraints = native_milp_constraints(view)
        valid = 0
        for bits in product((0, 1), repeat=8):
            selected = [p for p, bit in zip(view["variables"], bits) if bit]
            actual = validate_selection(scenario, selected)["valid"]
            values = constraints.A @ np.asarray(bits)
            expected = bool(np.all(values >= constraints.lb - 1e-8) and np.all(values <= constraints.ub + 1e-8))
            self.assertEqual(actual, expected)
            valid += actual
        self.assertEqual(valid, 4)

    def test_validator_recomputes_power_energy_occupancy_and_times(self):
        case = benchmark_cases()[0]
        model = build_shared_power_qubo(case["scenario"])
        schedule = solve_shared_power_exact(model)["schedule"]
        self.assertTrue(validate_selection(case["scenario"], schedule)["valid"])
        for change in ("energy", "gun", "deadline"):
            plans, scenario = deepcopy(schedule), deepcopy(case["scenario"])
            if change == "energy":
                plans[0]["power_kw_by_slot"] = (0, 50)
            elif change == "gun":
                plans[1]["gun"] = plans[0]["gun"]
            else:
                scenario["vehicles"][0]["deadline_minute"] = 30
            with self.subTest(change=change):
                self.assertFalse(validate_selection(scenario, plans)["valid"])

    def test_counts_decode_qiskit_order_and_never_invent_unmeasured_optimum(self):
        scenario = benchmark_cases()[0]["scenario"]
        view = candidate_view(scenario)
        # A x2 and B x5 form the valid 120-minute delayed plan, not the optimum.
        bits = [0, 0, 1, 0, 0, 1, 0, 0]
        counts = {"".join(map(str, reversed(bits))): 7, "00000000": 3}
        result = analyze_counts(view, counts, 90)
        self.assertEqual(result["best"]["total_flow_minutes"], 120)
        self.assertEqual(result["valid_samples"], 7)
        self.assertEqual(result["optimal_samples"], 0)
        self.assertEqual(result["bits"], bits)

    def test_structured_sampler_is_seeded_and_can_find_reference(self):
        scenario = benchmark_cases()[0]["scenario"]
        settings = {"shots": 256, "layers": 1, "iterations": 8, "restarts": 1}
        a = run_trial(scenario, "structured_random", 7, 90, settings)
        b = run_trial(scenario, "structured_random", 7, 90, settings)
        self.assertEqual(a["sample_counts"], b["sample_counts"])
        self.assertEqual(a["sample_count"], 256)
        self.assertEqual(a["best_total_flow_minutes"], 90)
        self.assertGreater(a["feasible_sample_fraction"], 0)
        self.assertGreaterEqual(a["timings"]["total_seconds"], a["timings"]["solve_seconds"])

    def test_small_report_checks_staleness_aggregates_and_sample_integrity(self):
        report = run_benchmark(seeds=[7], config={"layers": 1, "iterations": 8, "restarts": 1, "shots": 128})
        self.assertTrue(validate_report(report, require_full_protocol=False))
        with self.assertRaisesRegex(ValueError, "full benchmark protocol"):
            validate_report(report)
        self.assertEqual(report["cases"][0]["analytical_reference"]["uniform_bitstring_feasibility"], 4/256)
        self.assertEqual(report["cases"][0]["analytical_reference"]["structured_uniform_feasibility"], 4/16)
        bad = deepcopy(report); bad["source_hashes"]["src/quantum_scheduler.py"] = "stale"
        with self.assertRaisesRegex(ValueError, "Stale"):
            validate_report(bad, require_full_protocol=False)
        bad = deepcopy(report); bad["cases"][0]["summary"]["milp"]["median_average_minutes"] = 0
        with self.assertRaisesRegex(ValueError, "aggregates"):
            validate_report(bad, require_full_protocol=False)
        bad = deepcopy(report); bad["cases"][0]["plans"][0]["gun"] = 99
        with self.assertRaisesRegex(ValueError, "inputs/plans"):
            validate_report(bad, require_full_protocol=False)

    def test_release_gate_requires_a_best_observed_sample(self):
        report = run_benchmark(seeds=[7], config={"layers": 1, "iterations": 8, "restarts": 1, "shots": 128})
        case = report["cases"][0]
        run = next(r for r in case["runs"] if r["method"] == "structured_random")
        # Retain a valid optimum as the claimed answer, but remove it from observations.
        run.update(sample_counts={"00100100": 128}, sample_count=128, valid_samples=128,
                   optimal_samples=0, feasible_sample_fraction=1, optimal_sample_fraction=0)
        case["summary"] = summarize_runs(case["runs"])
        with self.assertRaisesRegex(ValueError, "best observed sample"):
            validate_report(report, require_full_protocol=False)

    def test_errors_remain_failures_without_a_reference_fallback(self):
        result = run_trial(benchmark_cases()[0]["scenario"], "qaoa", 0, 90,
                           {"layers": 0, "iterations": 8, "restarts": 1, "shots": 128})
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["valid_answer"])
        self.assertIsNone(result["best_total_flow_minutes"])
        with self.assertRaises(ValueError):
            run_benchmark(seeds=[])


if __name__ == "__main__":
    unittest.main()
