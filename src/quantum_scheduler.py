"""Booking bits -> QUBO -> Ising cost -> QAOA gates -> sampled schedules.

Aer executes every training circuit and the final measured circuit locally.
There is no exhaustive search or classical scheduling fallback in this module.
"""

from itertools import combinations
from math import isfinite, pi
from random import Random

from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import EstimatorV2
from scipy.optimize import minimize

from src.ev_scheduler import validate_scenario


def build_qubo(scenario, options, penalty=None):
    """Give each generated booking a bit and encode scheduling rules as costs.

    f(x) = constant + sum(linear[i]*x[i]) + sum(quadratic[i,j]*x[i]*x[j]).
    Expand P*(sum(bits_for_a_car)-1)**2 using x*x=x for binary x.
    Add P*x[i]*x[j] when two different cars want the same station and slot.
    """
    validate_scenario(scenario)
    vehicle_ids = [vehicle["id"] for vehicle in scenario["vehicles"]]
    if set(options) != set(vehicle_ids):
        raise ValueError("options must contain exactly the vehicle IDs")
    missing = [vehicle_id for vehicle_id in vehicle_ids if not options[vehicle_id]]
    if missing:
        raise ValueError(f"No feasible booking for: {', '.join(missing)}")

    # All booking scores are nonnegative. This bounds the cost of ANY valid
    # schedule without finding one or searching combinations in advance.
    score_bound = sum(max(booking["score"] for booking in options[v]) for v in vehicle_ids)
    if penalty is None:
        penalty = score_bound + 1.0
    if isinstance(penalty, bool) or not isinstance(penalty, (int, float)):
        raise ValueError("penalty must be a positive finite number")
    if not isfinite(penalty) or penalty <= 0:
        raise ValueError("penalty must be a positive finite number")

    variables = []
    groups = {}
    for vehicle_id in vehicle_ids:
        groups[vehicle_id] = []
        for booking in options[vehicle_id]:
            groups[vehicle_id].append(len(variables))
            variables.append(dict(booking))

    linear = [booking["score"] - penalty for booking in variables]
    quadratic = {}
    for indices in groups.values():
        for i, j in combinations(indices, 2):
            quadratic[i, j] = 2 * penalty

    for i, j in combinations(range(len(variables)), 2):
        first, second = variables[i], variables[j]
        if first["vehicle_id"] == second["vehicle_id"]:
            continue
        if (first["station_id"], first["slot_id"]) == (second["station_id"], second["slot_id"]):
            quadratic[i, j] = quadratic.get((i, j), 0) + penalty

    return {
        "variables": variables,
        "groups": groups,
        "penalty": float(penalty),
        "score_bound": score_bound,
        "constant": penalty * len(vehicle_ids),
        "linear": linear,
        "quadratic": quadratic,
    }


def _check_bits(model, bits):
    if len(bits) != len(model["variables"]) or any(bit not in (0, 1) for bit in bits):
        raise ValueError("Provide one binary value per booking, in qubit order")


def qubo_value(model, bits):
    """Evaluate a proposed bit string; this function does not search for one."""
    _check_bits(model, bits)
    return (
        model["constant"]
        + sum(coefficient * bits[i] for i, coefficient in enumerate(model["linear"]))
        + sum(coefficient * bits[i] * bits[j] for (i, j), coefficient in model["quadratic"].items())
    )


def qubo_to_ising(model):
    """Substitute x[i]=(1-Z[i])/2; retain the constant for reporting scores.

    A linear term L*x becomes L/2 - L*Z/2.
    A pair Q*x[i]*x[j] becomes Q/4*(1 - Z[i] - Z[j] + Z[i]*Z[j]).
    """
    z = [-coefficient / 2 for coefficient in model["linear"]]
    zz = {}
    offset = model["constant"] + sum(model["linear"]) / 2
    for (i, j), coefficient in model["quadratic"].items():
        offset += coefficient / 4
        z[i] -= coefficient / 4
        z[j] -= coefficient / 4
        zz[i, j] = coefficient / 4

    terms = [("Z", [i], coefficient) for i, coefficient in enumerate(z)]
    terms += [("ZZ", [i, j], coefficient) for (i, j), coefficient in zz.items()]
    operator = SparsePauliOp.from_sparse_list(terms, num_qubits=len(z)).simplify()
    # Normalization keeps circuit angles on a manageable scale. It changes
    # neither the ordering of scores nor which schedule minimizes the objective.
    scale = max(float(abs(coefficient)) for coefficient in operator.coeffs) or 1.0
    return {"z": z, "zz": zz, "offset": offset, "operator": operator, "scale": scale}


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


def build_qaoa_circuit(ising, layers=2):
    """Construct the actual H, RZ, RZZ, RX gates, without measurements.

    Each layer has two adjustable angles: gamma for cost and beta for mixing.
    RZ(theta)=exp(-i*theta*Z/2), so the cost rotation needs a factor of two.
    The constant offset is a global phase and can be left out of the circuit.
    """
    _positive_integer(layers, "layers")
    circuit = QuantumCircuit(ising["operator"].num_qubits, name="EV_QAOA")
    gamma = ParameterVector("gamma", layers)
    beta = ParameterVector("beta", layers)
    circuit.h(range(circuit.num_qubits))

    for layer in range(layers):
        # Cost unitary: exp(-i * gamma * normalized_cost_Hamiltonian).
        for qubit, coefficient in enumerate(ising["z"]):
            if coefficient:
                circuit.rz(2 * gamma[layer] * coefficient / ising["scale"], qubit)
        for (i, j), coefficient in ising["zz"].items():
            if coefficient:
                circuit.rzz(2 * gamma[layer] * coefficient / ising["scale"], i, j)

        # Mixer: rotates each qubit around X, redistributing amplitudes.
        for qubit in range(circuit.num_qubits):
            circuit.rx(2 * beta[layer], qubit)

    return circuit


def decode_bits(model, bits):
    """Check measured bookings independently of the penalty function."""
    _check_bits(model, bits)
    reasons = []
    for vehicle_id, indices in model["groups"].items():
        if sum(bits[i] for i in indices) != 1:
            reasons.append(f"{vehicle_id} needs exactly one booking")

    schedule = [booking for i, booking in enumerate(model["variables"]) if bits[i]]
    occupied = set()
    for booking in schedule:
        resource = (booking["station_id"], booking["slot_id"])
        if resource in occupied:
            reasons.append(f"Double booking at {resource[0]} / {resource[1]}")
        occupied.add(resource)
    return {"valid": not reasons, "reasons": reasons, "schedule": schedule}


def summarize_counts(model, counts):
    """Decode ONLY measured strings, correcting Qiskit's displayed bit order."""
    samples = []
    for bitstring, count in counts.items():
        # Qiskit displays q[n-1]...q[0]. Our booking list is q[0]...q[n-1].
        bits = [int(bit) for bit in bitstring[::-1]]
        decoded = decode_bits(model, bits)
        samples.append({
            "qiskit_bitstring": bitstring,
            "bits": bits,
            "count": count,
            "qubo_score": qubo_value(model, bits),
            **decoded,
        })
    samples.sort(key=lambda sample: (-sample["count"], sample["qiskit_bitstring"]))
    feasible = [sample for sample in samples if sample["valid"]]
    valid_shots = sum(sample["count"] for sample in feasible)
    total_shots = sum(counts.values())

    result = {
        "status": "no_feasible_sample",
        "reason": "No valid schedule was sampled; this does not prove the problem is infeasible",
        "schedule": [],
        "bits": None,
        "total_electricity_cost_rupees": None,
        "total_waiting_minutes": None,
        "total_score": None,
        "valid_shots": valid_shots,
        "valid_sample_fraction": valid_shots / total_shots if total_shots else 0,
        "samples": samples,
        "counts": dict(counts),
    }
    if feasible:
        # Select among quantum samples, never among unmeasured bit strings.
        best = min(feasible, key=lambda sample: (
            sum(booking["score"] for booking in sample["schedule"]), -sample["count"]
        ))
        result.update({
            "status": "feasible",
            "reason": None,
            "schedule": best["schedule"],
            "bits": best["bits"],
            "total_electricity_cost_rupees": sum(
                booking["electricity_cost_rupees"] for booking in best["schedule"]
            ),
            "total_waiting_minutes": sum(booking["waiting_minutes"] for booking in best["schedule"]),
            "total_score": sum(booking["score"] for booking in best["schedule"]),
        })
    return result


def solve_qaoa(model, *, layers=2, shots=4096, iterations=160, restarts=3, seed=7, progress=None):
    """Train a QAOA circuit on Aer, then sample its best observed parameters.

    COBYLA adjusts angles, not vehicle bookings. Training uses Aer Estimator's
    exact expectation (precision=0), without finite-shot noise. `shots` controls
    the final measured circuit only. `iterations` budgets evaluations per restart.
    """
    for label, value in (("layers", layers), ("shots", shots), ("iterations", iterations), ("restarts", restarts)):
        _positive_integer(value, label)
    if iterations < 2 * layers + 2:
        raise ValueError("iterations must be at least 2*layers + 2 for COBYLA")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")

    ising = qubo_to_ising(model)
    circuit = build_qaoa_circuit(ising, layers)
    estimator = EstimatorV2(options={"backend_options": {
        "method": "statevector", "max_parallel_threads": 1,
    }})
    normalized_cost = ising["operator"] / ising["scale"]
    rng = Random(seed)
    history = []
    best_energy = float("inf")
    best_angles = None

    for restart in range(restarts):
        evaluation = 0

        def objective(angles):
            nonlocal best_energy, best_angles, evaluation
            pub = (circuit, normalized_cost, angles)
            energy = float(estimator.run([pub], precision=0).result()[0].data.evs)
            evaluation += 1
            expected_score = energy * ising["scale"] + ising["offset"]
            history.append({"restart": restart + 1, "evaluation": evaluation, "expected_score": expected_score})
            if energy < best_energy:
                best_energy = energy
                best_angles = [float(angle) for angle in angles]
            return energy

        # Qiskit orders this circuit's parameters as beta[0..p-1], gamma[0..p-1].
        initial_angles = [rng.uniform(0, pi) for _ in circuit.parameters]
        optimization = minimize(objective, initial_angles, method="COBYLA", options={
            "maxiter": iterations, "rhobeg": 0.5, "tol": 1e-4,
        })
        if progress is not None:
            progress({
                "restart": restart + 1,
                "evaluations": evaluation,
                "initial_expected_score": history[-evaluation]["expected_score"],
                "best_expected_score": best_energy * ising["scale"] + ising["offset"],
                "optimizer_message": str(optimization.message),
            })

    measured = circuit.assign_parameters(best_angles)
    measured.measure_all()
    simulator = AerSimulator(method="statevector", max_parallel_threads=1)
    counts = simulator.run(measured, shots=shots, seed_simulator=seed).result().get_counts()
    result = summarize_counts(model, counts)
    result.update({
        "method": "QAOA on local Qiskit Aer simulator",
        "layers": layers,
        "shots": shots,
        "seed": seed,
        "history": history,
        "parameter_order": [str(parameter) for parameter in circuit.parameters],
        "angles": best_angles,
        "best_expected_score": best_energy * ising["scale"] + ising["offset"],
    })
    return result
