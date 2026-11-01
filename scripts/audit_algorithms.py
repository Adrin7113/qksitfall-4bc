#!/usr/bin/env python3
"""Read-only exhaustive audit of the EV charging prototypes.

Run using the project's Python, for example:
  .venv/bin/python scripts/audit_algorithms.py

No project or website files are written. Random cases are deterministic.
The physical oracle recomputes occupancy, energy, completion and capacity
directly from power profiles; it never reads the QUBO's conflict edges.
"""

import argparse
from itertools import combinations, product
import json
from math import isclose
from pathlib import Path
from random import Random
import sys


def polynomial(model, bits):
    return (model["constant"]
            + sum(c * bit for c, bit in zip(model["linear"], bits))
            + sum(c * bits[i] * bits[j] for (i, j), c in model["quadratic"].items()))


def physical_oracle(scenario, plans):
    """Independent whole-schedule checker, including aggregate module power."""
    vehicles = {v["id"]: v for v in scenario["vehicles"]}
    modules = {m["id"]: m for m in scenario["modules"]}
    if any(sum(p["vehicle_id"] == vid for p in plans) != 1 for vid in vehicles):
        return False, None
    occupied = set()
    module_power = {mid: [0] * scenario["num_slots"] for mid in modules}
    score = 0
    for plan in plans:
        vehicle = vehicles[plan["vehicle_id"]]
        powers = plan["power_kw_by_slot"]
        if len(powers) != scenario["num_slots"] or plan["gun"] not in (0, 1):
            return False, None
        if any(p < 0 or p > vehicle["max_power_kw"] + 1e-8 for p in powers):
            return False, None
        energy = sum(powers) * scenario["slot_minutes"] / 60
        if not isclose(energy, vehicle["required_energy_kwh"], rel_tol=0, abs_tol=1e-8):
            return False, None
        active = [t for t, p in enumerate(powers) if p > 0]
        if not active:
            return False, None
        first, end = active[0], active[-1] + 1
        start = scenario["start_minute"] + first * scenario["slot_minutes"]
        completion = scenario["start_minute"] + end * scenario["slot_minutes"]
        if start < vehicle["arrival_minute"] or completion > vehicle["deadline_minute"]:
            return False, None
        for t in range(first, end):
            key = (plan["module_id"], plan["gun"], t)
            if key in occupied:
                return False, None
            occupied.add(key)
        for t, kw in enumerate(powers):
            module_power[plan["module_id"]][t] += kw
        score += completion - vehicle["arrival_minute"]
    if any(kw > modules[mid]["power_kw"] + 1e-8 for mid, powers in module_power.items() for kw in powers):
        return False, None
    return True, score


def independent_pair_conflict(scenario, a, b):
    if a["module_id"] != b["module_id"]:
        return False
    pa, pb = a["power_kw_by_slot"], b["power_kw_by_slot"]
    active_a = [t for t, p in enumerate(pa) if p > 0]
    active_b = [t for t, p in enumerate(pb) if p > 0]
    overlap = max(active_a[0], active_b[0]) <= min(active_a[-1], active_b[-1])
    capacity = next(m["power_kw"] for m in scenario["modules"] if m["id"] == a["module_id"])
    return ((a["gun"] == b["gun"] and overlap)
            or any(x + y > capacity + 1e-8 for x, y in zip(pa, pb)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--cases", type=int, default=80)
    parser.add_argument("--max-bits", type=int, default=14)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.root).resolve()))
    from main import sample_scenario
    from shared_power_demo import sample_shared_power_scenario
    from src.ev_scheduler import generate_options
    from src.shared_power_scheduler import (
        _profiles, build_shared_power_qubo, decode_shared_power_bits,
        generate_shared_power_options, solve_shared_power_exact,
    )

    # Regressions for issues found during the audit.
    boundary_checks = 0
    scenario = sample_shared_power_scenario()
    scenario["vehicles"][0]["required_energy_kwh"] = 37.5000001
    try:
        build_shared_power_qubo(scenario)
    except ValueError as error:
        assert "multiple" in str(error), error
    else:
        raise AssertionError("Misaligned energy was accepted")
    boundary_checks += 1

    for changed in ("car", "module"):
        scenario = sample_shared_power_scenario()
        if changed == "car":
            scenario["vehicles"][1]["max_power_kw"] = 24.9999999
        else:
            scenario["modules"][0]["power_kw"] = 24.9999999
        try:
            build_shared_power_qubo(scenario)
        except ValueError as error:
            assert "No grid-feasible" in str(error), error
        else:
            raise AssertionError(f"Invalid {changed} power ceiling generated a model")
        boundary_checks += 1

    scenario = sample_shared_power_scenario()
    scenario.update(num_slots=1440, slot_minutes=1)
    for vehicle in scenario["vehicles"]:
        vehicle["deadline_minute"] = 1440
    try:
        generate_shared_power_options(scenario, max_options_per_vehicle=1)
    except ValueError as error:
        assert "Too many candidate" in str(error), error
    else:
        raise AssertionError("Long-horizon candidate guard did not trigger")
    boundary_checks += 1

    scenario = sample_scenario()
    scenario["vehicles"][0]["max_power_kw"] = 5
    assert generate_options(scenario)["options"]["A"] == [], "Legacy model ignored the car ceiling"
    boundary_checks += 1
    scenario["vehicles"][0]["max_power_kw"] = 10.5
    first = generate_options(scenario)["options"]["A"][0]
    assert first["charging_power_kw"] == 10.5
    assert isclose(first["charging_duration_minutes"], first["charging_energy_kwh"] / 10.5 * 60)
    boundary_checks += 1

    # Independent completeness/order check of the new iterative profile search.
    profile_cases = 0
    for slots in range(5):
        for cap in range(4):
            for required in range(slots * cap + 2):
                expected = [p for p in product(range(cap + 1), repeat=slots) if sum(p) == required]
                actual = list(_profiles(slots, required, cap))
                assert actual == expected, (slots, cap, required, actual, expected)
                profile_cases += 1

    rng = Random(args.seed)
    checked = states = skipped_size = skipped_infeasible = feasible = 0
    for case in range(args.cases):
        slots, cars = rng.randint(1, 3), rng.randint(1, 3)
        scenario = {
            "start_minute": 0, "slot_minutes": 30, "num_slots": slots, "power_step_kw": 25,
            "modules": [{"id": "M1", "power_kw": rng.choice([25, 40, 50, 60])}],
            "vehicles": [{"id": str(i), "required_energy_kwh": rng.randint(1, slots) * 12.5,
                          "max_power_kw": rng.choice([25, 40, 50]), "arrival_minute": 0,
                          "deadline_minute": slots * 30} for i in range(cars)],
        }
        try:
            model = build_shared_power_qubo(scenario)
        except ValueError:
            skipped_infeasible += 1
            continue
        if len(model["variables"]) > args.max_bits:
            skipped_size += 1
            continue
        valid_scores, invalid_scores = [], []
        for bits in product((0, 1), repeat=len(model["variables"])):
            selected = [p for p, bit in zip(model["variables"], bits) if bit]
            valid, physical_score = physical_oracle(scenario, selected)
            assert decode_shared_power_bits(model, bits)["valid"] == valid, (case, bits, scenario)
            one_hot = sum((sum(p["vehicle_id"] == v["id"] for p in selected) - 1) ** 2
                          for v in scenario["vehicles"])
            conflicts = sum(independent_pair_conflict(scenario, a, b) for a, b in combinations(selected, 2)
                            if a["vehicle_id"] != b["vehicle_id"])
            expected = sum(p["score"] for p in selected) + model["penalty"] * (one_hot + conflicts)
            score = polynomial(model, bits)
            assert isclose(score, expected, abs_tol=1e-8), (case, bits, score, expected)
            if valid:
                assert isclose(score, physical_score, abs_tol=1e-8)
                valid_scores.append(score)
            else:
                invalid_scores.append(score)
            states += 1
        reference = solve_shared_power_exact(model)
        if valid_scores:
            assert min(valid_scores) > 0
            assert min(valid_scores) < min(invalid_scores)
            assert max(valid_scores) < min(invalid_scores)
            assert reference["status"] == "optimal"
            assert reference["total_score"] == min(valid_scores)
            feasible += 1
        else:
            assert reference["status"] == "infeasible"
        checked += 1

    print(json.dumps({
        "status": "passed", "seed": args.seed, "requested_scenarios": args.cases,
        "exhaustively_checked_scenarios": checked, "feasible_scenarios": feasible,
        "binary_assignments_checked": states, "skipped_oversize": skipped_size,
        "skipped_individually_infeasible": skipped_infeasible,
        "iterative_profile_completeness_cases": profile_cases,
        "boundary_regressions": boundary_checks,
    }, indent=2))


if __name__ == "__main__":
    main()
