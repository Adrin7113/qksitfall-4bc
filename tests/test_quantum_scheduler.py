"""Verify the mathematical encoding and actual circuit, not just its output."""

from itertools import product
from math import cos, sin, sqrt
import unittest

from qiskit.quantum_info import Statevector

from main import sample_scenario
from src.ev_scheduler import generate_options
from src.quantum_scheduler import (
    build_qaoa_circuit, build_qubo, decode_bits, qubo_to_ising,
    qubo_value, solve_qaoa, summarize_counts,
)
from tests.test_ev_scheduler import small_scenario


class QuantumEncodingTests(unittest.TestCase):
    def setUp(self):
        scenario = sample_scenario()
        self.model = build_qubo(scenario, generate_options(scenario)["options"])

    def test_qubo_matches_independent_scheduling_rules_for_every_bitstring(self):
        penalty = self.model["penalty"]
        costs = [22.05, 26.65, 33, 37, 19.65]
        for bits in product((0, 1), repeat=5):
            with self.subTest(bits=bits):
                booking_cost = sum(cost * bit for cost, bit in zip(costs, bits))
                violations = (sum(bits[:4]) - 1)**2 + (bits[4] - 1)**2 + bits[0]*bits[4]
                self.assertAlmostEqual(qubo_value(self.model, bits), booking_cost + penalty*violations)

    def test_hamiltonian_preserves_all_qubo_energies_and_bit_order(self):
        ising = qubo_to_ising(self.model)
        diagonal = ising["operator"].to_matrix().diagonal()
        for bits in product((0, 1), repeat=5):
            # q0 is the least significant bit in Qiskit's matrix basis.
            basis_index = sum(bit << i for i, bit in enumerate(bits))
            self.assertAlmostEqual(diagonal[basis_index].real + ising["offset"], qubo_value(self.model, bits))

    def test_cost_gates_apply_the_correct_relative_phases(self):
        ising = qubo_to_ising(self.model)
        circuit = build_qaoa_circuit(ising, layers=1)
        angles = {p: (0 if str(p).startswith("beta") else 0.37) for p in circuit.parameters}
        state = Statevector.from_instruction(circuit.assign_parameters(angles))
        for bits in product((0, 1), repeat=5):
            basis_index = sum(bit << i for i, bit in enumerate(bits))
            phase = -0.37 * (qubo_value(self.model, bits) - ising["offset"]) / ising["scale"]
            expected = complex(cos(phase), sin(phase)) / sqrt(32)
            self.assertAlmostEqual(state.data[basis_index].real, expected.real)
            self.assertAlmostEqual(state.data[basis_index].imag, expected.imag)

    def test_zero_angles_prepare_uniform_superposition(self):
        circuit = build_qaoa_circuit(qubo_to_ising(self.model), layers=2)
        state = Statevector.from_instruction(circuit.assign_parameters([0]*4))
        for probability in state.probabilities():
            self.assertAlmostEqual(probability, 1/32)

    def test_safe_penalty_exceeds_every_valid_schedule_cost(self):
        self.assertAlmostEqual(self.model["score_bound"], 56.65)
        self.assertAlmostEqual(self.model["penalty"], 57.65)
        valid_scores, invalid_scores = [], []
        for bits in product((0, 1), repeat=5):
            bucket = valid_scores if decode_bits(self.model, bits)["valid"] else invalid_scores
            bucket.append(qubo_value(self.model, bits))
        self.assertLess(max(valid_scores), min(invalid_scores))
        self.assertAlmostEqual(min(valid_scores), 46.3)

    def test_qiskit_counts_are_reversed_into_booking_order(self):
        result = summarize_counts(self.model, {"10010": 7, "00000": 3})
        self.assertEqual(result["bits"], [0, 1, 0, 0, 1])
        self.assertAlmostEqual(result["total_score"], 46.3)
        self.assertEqual(result["valid_shots"], 7)
        self.assertAlmostEqual(result["valid_sample_fraction"], 0.7)

    def test_selection_never_invents_a_schedule_that_was_not_sampled(self):
        # Only A/South/early + B/North/early was measured, not the optimum.
        result = summarize_counts(self.model, {"10100": 10})
        self.assertEqual(result["bits"], [0, 0, 1, 0, 1])
        self.assertAlmostEqual(result["total_score"], 52.65)

    def test_invalid_samples_do_not_trigger_a_classical_fallback(self):
        result = summarize_counts(self.model, {"10001": 10, "00000": 10})
        self.assertEqual(result["status"], "no_feasible_sample")
        self.assertEqual(result["schedule"], [])
        self.assertIsNone(result["total_score"])
        self.assertIn("does not prove", result["reason"])

    def test_model_validation_and_bad_bits(self):
        scenario = sample_scenario()
        options = generate_options(scenario)["options"]
        for penalty in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(penalty=penalty), self.assertRaises(ValueError):
                build_qubo(scenario, options, penalty=penalty)
        with self.assertRaises(ValueError):
            qubo_value(self.model, [1, 0])
        with self.assertRaises(ValueError):
            decode_bits(self.model, [0, 1, 0, 0, 2])
        options["B"] = []
        with self.assertRaisesRegex(ValueError, "No feasible booking"):
            build_qubo(scenario, options)


class QAOAExecutionTests(unittest.TestCase):
    def test_real_aer_training_and_sampling(self):
        scenario = sample_scenario()
        model = build_qubo(scenario, generate_options(scenario)["options"])
        updates = []
        result = solve_qaoa(model, layers=2, iterations=40, restarts=2, shots=1024, seed=7, progress=updates.append)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(sum(result["counts"].values()), 1024)
        self.assertEqual(len(updates), 2)
        self.assertEqual(len(result["angles"]), 4)
        self.assertLess(result["best_expected_score"], result["history"][0]["expected_score"])
        self.assertTrue(decode_bits(model, result["bits"])["valid"])
        measured_valid_scores = [sample["qubo_score"] for sample in result["samples"] if sample["valid"]]
        self.assertAlmostEqual(result["total_score"], min(measured_valid_scores))

    def test_single_qubit_model_runs_without_two_qubit_gates(self):
        scenario = small_scenario()
        model = build_qubo(scenario, generate_options(scenario)["options"])
        result = solve_qaoa(model, layers=1, iterations=40, restarts=1, shots=128, seed=7)
        self.assertEqual(result["bits"], [1])
        self.assertAlmostEqual(result["total_score"], 20)

    def test_impossible_global_schedule_cannot_be_reported_as_feasible(self):
        scenario = small_scenario()
        scenario["vehicles"].append({**scenario["vehicles"][0], "id": "B"})
        scenario["travel"]["B"] = {"North": {"distance_km": 0, "duration_minutes": 0}}
        model = build_qubo(scenario, generate_options(scenario)["options"])
        result = solve_qaoa(model, layers=1, iterations=20, restarts=1, shots=128, seed=7)
        self.assertEqual(result["status"], "no_feasible_sample")
        self.assertEqual(result["valid_shots"], 0)

    def test_invalid_training_configuration(self):
        scenario = small_scenario()
        model = build_qubo(scenario, generate_options(scenario)["options"])
        for settings in ({"shots": 0}, {"layers": 0}, {"iterations": 1}, {"seed": -1}, {"restarts": True}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                solve_qaoa(model, **settings)


if __name__ == "__main__":
    unittest.main()
