"""Build and verify the shared-power QUBO; optionally execute the existing QAOA."""

import argparse

from src.shared_power_scheduler import build_shared_power_qubo, solve_shared_power_exact


def sample_shared_power_scenario():
    """Small eight-bit instance: 50 kW module, 50/25 kW vehicle limits.

    At 25 kW for 30 minutes, one energy unit is 12.5 kWh. A needs three
    units, B needs one. This coarse grid keeps the quantum example small.
    """
    return {
        "start_minute": 0, "slot_minutes": 30, "num_slots": 2, "power_step_kw": 25,
        "modules": [{"id": "M1", "power_kw": 50, "gun_count": 2}],
        "vehicles": [
            {"id": "A", "required_energy_kwh": 37.5, "max_power_kw": 50,
             "arrival_minute": 0, "deadline_minute": 60},
            {"id": "B", "required_energy_kwh": 12.5, "max_power_kw": 25,
             "arrival_minute": 0, "deadline_minute": 60},
        ],
    }


def _print_schedule(result):
    if result["status"] not in ("optimal", "feasible"):
        print(f"No schedule: {result['status']}")
        return
    for plan in result["schedule"]:
        print(f"  {plan['vehicle_id']} -> {plan['module_id']} / gun {plan['gun']}: "
              f"{list(plan['power_kw_by_slot'])} kW; finishes at minute {plan['completion_minute']}")
    print(f"  Total arrival-to-completion: {result['total_flow_minutes']:g} minutes")
    print(f"  Average arrival-to-completion: {result['average_flow_minutes']:g} minutes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qaoa", action="store_true", help="Also train/sample the existing local Aer circuit")
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--restarts", type=int, default=2)
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    model = build_shared_power_qubo(sample_shared_power_scenario())
    print("SHARED-POWER QUBO: one bit per complete charging plan")
    print("Each entry below is power in one 30-minute slot; guns are numbered 0 and 1.")
    for i, plan in enumerate(model["variables"]):
        print(f"x{i}: {plan['vehicle_id']} / {plan['module_id']} / gun {plan['gun']} / "
              f"{list(plan['power_kw_by_slot'])} kW / flow cost {plan['score']} minutes")
    print(f"\n{len(model['variables'])} bits; QAOA would use the same number of qubits.")
    print(f"Safe penalty: {model['penalty']:g}; feasible score bound: {model['score_bound']:g}")
    print(f"F(x) = {model['constant']:g} + sum(L[i]*x[i]) + sum(Q[i,j]*x[i]*x[j])")
    print(f"L = {model['linear']}")
    print(f"Q = {model['quadratic']}")
    print("\nCLASSICAL EXACT REFERENCE (separate from quantum execution)")
    _print_schedule(solve_shared_power_exact(model))
    if args.qaoa:
        from src.quantum_scheduler import solve_qaoa
        print("\nQAOA: train and sample the shared-power model on local Aer", flush=True)
        try:
            result = solve_qaoa(model, layers=args.layers, iterations=args.iterations,
                                restarts=args.restarts, shots=args.shots, seed=args.seed)
        except ValueError as error:
            parser.error(str(error))
        print(f"Valid measurements: {result['valid_shots']}/{args.shots}")
        _print_schedule(result)
        print("The quantum result uses measured strings only; the reference is never used as a fallback.")
        if result["status"] != "feasible":
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
