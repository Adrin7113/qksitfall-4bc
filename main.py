"""Learn and run quantum EV scheduling with an explicit Qiskit QAOA circuit."""

import argparse
from time import perf_counter

from src.ev_scheduler import generate_options


def sample_scenario():
    """Return fresh, editable input data; no booking options are hardcoded."""
    return {
        "vehicles": [
            {
                "id": "A",
                "battery_capacity_kwh": 50,
                "current_charge_percent": 30,
                "target_charge_percent": 50,
                "consumption_kwh_per_km": 0.2,
                "available_from_minute": 7 * 60 + 45,
                "deadline_minute": 10 * 60,
            },
            {
                "id": "B",
                "battery_capacity_kwh": 50,
                "current_charge_percent": 12,
                "target_charge_percent": 30,
                "consumption_kwh_per_km": 0.2,
                "available_from_minute": 7 * 60 + 50,
                "deadline_minute": 9 * 60,
            },
        ],
        "stations": [
            {"id": "North", "power_kw": 11, "prices_per_kwh": {"early": 2, "late": 1}},
            {"id": "South", "power_kw": 11, "prices_per_kwh": {"early": 3, "late": 2}},
        ],
        "slots": [
            {"id": "early", "start_minute": 8 * 60, "end_minute": 9 * 60},
            {"id": "late", "start_minute": 9 * 60, "end_minute": 10 * 60},
        ],
        "travel": {
            "A": {
                "North": {"distance_km": 2, "duration_minutes": 10},
                "South": {"distance_km": 5, "duration_minutes": 15},
            },
            "B": {
                "North": {"distance_km": 1, "duration_minutes": 5},
                "South": {"distance_km": 20, "duration_minutes": 30},
            },
        },
        "reserve_percent": 5,
        "waiting_weight_per_minute": 0.25,
    }


def format_time(minutes):
    """Display integer or fractional minutes without rounding calculations."""
    total_seconds = round(minutes * 60)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main():
    # Keep quantum imports here so importing sample_scenario() remains lightweight.
    from src.quantum_scheduler import build_qaoa_circuit, build_qubo, qubo_to_ising, solve_qaoa

    parser = argparse.ArgumentParser(description="Quantum EV scheduling: QUBO -> QAOA -> sampled bookings")
    parser.add_argument("--layers", type=int, default=2, help="QAOA depth p; two angles per layer")
    parser.add_argument("--shots", type=int, default=4096, help="Final circuit measurement repetitions")
    parser.add_argument("--iterations", type=int, default=160, help="Training evaluation budget per restart")
    parser.add_argument("--restarts", type=int, default=3, help="Number of independently initialized angle searches")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for initialization and final sampling")
    parser.add_argument("--penalty", type=float, default=None, help="Override the automatically calculated constraint penalty")
    parser.add_argument("--show-circuit", action="store_true", help="Print the actual parameterized H/RZ/RZZ/RX circuit")
    args = parser.parse_args()
    scenario = sample_scenario()
    generated = generate_options(scenario)
    missing = [vehicle_id for vehicle_id, options in generated["options"].items() if not options]
    if missing:
        print(f"No feasible booking for: {', '.join(missing)}. No circuit was run.")
        return 2

    print("QUANTUM CHECKPOINT 1: One qubit per feasible booking")
    try:
        model = build_qubo(scenario, generated["options"], penalty=args.penalty)
        ising = qubo_to_ising(model)
        circuit = build_qaoa_circuit(ising, layers=args.layers)
    except ValueError as error:
        parser.error(str(error))
    for i, booking in enumerate(model["variables"]):
        print(
            f"q{i} / x{i}: {booking['vehicle_id']} -> {booking['station_id']} / {booking['slot_id']}, "
            f"booking score {booking['score']:.2f}"
        )

    print("\nQUANTUM CHECKPOINT 2: QUBO = booking scores + constraint penalties")
    print(f"Penalty P = {model['penalty']:.2f}; valid schedule score bound = {model['score_bound']:.2f}")
    if model["penalty"] <= model["score_bound"]:
        print("Custom penalty is below the safe bound; low-energy samples may violate constraints.")
    for vehicle_id, indices in model["groups"].items():
        terms = " + ".join(f"x{i}" for i in indices)
        print(f"{vehicle_id}: P * ({terms} - 1)^2 enforces exactly one booking")
    print("Different cars sharing a station and slot also incur P*x_i*x_j.")

    print("\nQUANTUM CHECKPOINT 3: Map x=(1-Z)/2 into circuit operations")
    print(f"{circuit.num_qubits} qubits; {args.layers} layers; {circuit.num_parameters} adjustable angles")
    print(f"Cost normalization scale: {ising['scale']:.4f}; score offset: {ising['offset']:.4f}")
    print("H gates prepare superposition; RZ/RZZ encode cost; RX gates mix amplitudes.")
    if args.show_circuit:
        print(circuit.draw(output="text", fold=110))

    print("\nQUANTUM CHECKPOINT 4: Train circuit angles with COBYLA")
    print("Training uses exact local Aer expectation values; shots apply to final measurements.")

    def report(update):
        print(
            f"Restart {update['restart']}: {update['evaluations']} circuit evaluations; "
            f"initial expected score {update['initial_expected_score']:.3f}; "
            f"best expected score so far {update['best_expected_score']:.3f}",
            flush=True,
        )

    started = perf_counter()
    try:
        result = solve_qaoa(
            model, layers=args.layers, shots=args.shots, iterations=args.iterations,
            restarts=args.restarts, seed=args.seed, progress=report,
        )
    except ValueError as error:
        parser.error(str(error))
    elapsed = perf_counter() - started

    print("\nQUANTUM CHECKPOINT 5: Measure and validate sampled schedules")
    print(f"Valid shots: {result['valid_shots']}/{args.shots} ({result['valid_sample_fraction']:.1%})")
    print("Most frequent measurements (Qiskit displays the highest-index qubit first):")
    for sample in result["samples"][:8]:
        validity = "valid" if sample["valid"] else "invalid"
        print(
            f"  {sample['qiskit_bitstring']}: {sample['count']} shots; "
            f"{validity}; QUBO score {sample['qubo_score']:.2f}"
        )

    print("\nQUANTUM CHECKPOINT 6: Best feasible schedule actually sampled")
    if result["status"] != "feasible":
        print(result["reason"])
        return 2
    print(f"Selected bits in booking order q0, q1, ...: {result['bits']}")
    for booking in result["schedule"]:
        print(
            f"Car {booking['vehicle_id']} -> {booking['station_id']}, "
            f"reserve {format_time(booking['start_minute'])}-{format_time(booking['end_minute'])}; "
            f"charging completes {format_time(booking['completion_minute'])}"
        )
    print(f"Electricity bill: Rs {result['total_electricity_cost_rupees']:.2f}")
    print(f"Total waiting: {result['total_waiting_minutes']} minutes")
    print(f"Sampled schedule score: {result['total_score']:.2f} points")
    print(f"QAOA training and sampling runtime: {elapsed:.3f} seconds")
    print("Execution: local Aer simulation. This run does not certify a global optimum.")
    print("Learn next: src/quantum_scheduler.py; improve --layers, --iterations, --restarts, --shots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
