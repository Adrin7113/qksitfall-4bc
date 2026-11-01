"""Dual-gun module scheduling as a binary, candidate-plan QUBO.

This module uses only the standard library. Candidate generation is classical
preprocessing, not a scheduling solver. A bit selects a complete charging plan:
one fixed module/gun and a time-varying power profile on a discrete grid.
"""

from copy import deepcopy
from itertools import combinations, product
from math import floor, isclose, isfinite, prod


TOLERANCE = 1e-8


def _number(value, label, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f"{label} must be a {'positive' if positive else 'nonnegative'} finite number")


def _integer(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        raise ValueError(f"{label} must be a {'positive' if positive else 'nonnegative'} integer")


def _records(records, label):
    if not isinstance(records, list) or not records:
        raise ValueError(f"{label} must be a nonempty list")
    ids = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"].strip():
            raise ValueError(f"{label} need nonempty string IDs")
        if record["id"] in ids:
            raise ValueError(f"{label} contain duplicate ID {record['id']}")
        ids.add(record["id"])


def validate_shared_power_scenario(scenario):
    """Reject unsupported assumptions instead of silently rounding energy."""
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a dictionary")
    for key in ("vehicles", "modules", "start_minute", "slot_minutes", "num_slots", "power_step_kw"):
        if key not in scenario:
            raise ValueError(f"scenario is missing {key!r}")
    _records(scenario["vehicles"], "vehicles")
    _records(scenario["modules"], "modules")
    _integer(scenario["start_minute"], "start_minute")
    _integer(scenario["slot_minutes"], "slot_minutes", positive=True)
    _integer(scenario["num_slots"], "num_slots", positive=True)
    _number(scenario["power_step_kw"], "power_step_kw", positive=True)
    energy_step = scenario["power_step_kw"] * scenario["slot_minutes"] / 60
    for module in scenario["modules"]:
        _number(module.get("power_kw"), f"module {module['id']} power_kw", positive=True)
        # Pair conflicts are sufficient for a two-gun module. Supporting three
        # or more simultaneous guns requires aggregate capacity constraints.
        if type(module.get("gun_count", 2)) is not int or module.get("gun_count", 2) != 2:
            raise ValueError("This encoding requires exactly two guns per module")
    for vehicle in scenario["vehicles"]:
        label = f"vehicle {vehicle['id']}"
        _number(vehicle.get("required_energy_kwh"), f"{label} required_energy_kwh", positive=True)
        _number(vehicle.get("max_power_kw"), f"{label} max_power_kw", positive=True)
        _integer(vehicle.get("arrival_minute"), f"{label} arrival_minute")
        _integer(vehicle.get("deadline_minute"), f"{label} deadline_minute")
        if vehicle["arrival_minute"] >= vehicle["deadline_minute"]:
            raise ValueError(f"{label} arrival must precede its deadline")
        units = vehicle["required_energy_kwh"] / energy_step
        # Compare in kWh, matching the decoder. A tolerance on unit counts
        # would become a different physical tolerance when the grid changes.
        if round(units) < 1 or not isclose(vehicle["required_energy_kwh"], round(units) * energy_step,
                                         rel_tol=0, abs_tol=TOLERANCE):
            raise ValueError(f"{label} energy must be a multiple of {energy_step:g} kWh; use a finer grid")
    # No lower shared site cap is encoded in this first model. Pairwise module
    # conflicts cannot represent a capacity violation involving three modules.
    if "site_power_kw" in scenario:
        _number(scenario["site_power_kw"], "site_power_kw", positive=True)
        if scenario["site_power_kw"] + TOLERANCE < sum(m["power_kw"] for m in scenario["modules"]):
            raise ValueError("A binding shared site_power_kw limit needs an aggregate-capacity encoding")


def _profiles(slot_count, required_units, max_units):
    """Yield all exact-energy profiles, including delayed starts and pauses.

    Search stops as soon as energy is satisfied; trailing slots are zero.
    Enumerating these profiles is exponential in the horizon in general.
    """
    # Explicit depth-first stack preserves lexicographic order without Python's
    # recursion-depth limit, so the caller's candidate budget works on long
    # horizons too. Iterators keep the stack bounded by the horizon length.
    profile = [0] * slot_count
    stack = [(0, required_units, None)]
    while stack:
        index, remaining, choices = stack[-1]
        if choices is None:
            if remaining == 0:
                yield tuple(profile[:index]) + (0,) * (slot_count - index)
                stack.pop()
                continue
            if index == slot_count or remaining > (slot_count - index) * max_units:
                stack.pop()
                continue
            minimum = max(0, remaining - (slot_count - index - 1) * max_units)
            choices = iter(range(minimum, min(remaining, max_units) + 1))
            stack[-1] = (index, remaining, choices)
        units = next(choices, None)
        if units is None:
            stack.pop()
        else:
            profile[index] = units
            stack.append((index + 1, remaining - units, None))


def generate_shared_power_options(scenario, *, max_options_per_vehicle=1000):
    """Build physically admissible individual plans; never choose between cars.

    A car stays on its chosen gun from its first positive-power slot to its
    completion, including any zero-power pauses between them. It can leave as
    soon as it finishes. Slot ends are the allowed completion instants.
    """
    validate_shared_power_scenario(scenario)
    _integer(max_options_per_vehicle, "max_options_per_vehicle", positive=True)
    start, duration, count = (scenario[k] for k in ("start_minute", "slot_minutes", "num_slots"))
    step = scenario["power_step_kw"]
    energy_step = step * duration / 60
    options = {vehicle["id"]: [] for vehicle in scenario["vehicles"]}
    for vehicle in scenario["vehicles"]:
        available = [t for t in range(count)
                     if start + t * duration >= vehicle["arrival_minute"]
                     and start + (t + 1) * duration <= vehicle["deadline_minute"]]
        if not available:
            continue
        required_units = round(vehicle["required_energy_kwh"] / energy_step)
        for module in scenario["modules"]:
            max_units = floor((min(vehicle["max_power_kw"], module["power_kw"]) + TOLERANCE) / step)
            for profile in _profiles(len(available), required_units, max_units):
                full_profile = (0,) * available[0] + profile + (0,) * (count - available[-1] - 1)
                nonzero = [t for t, units in enumerate(full_profile) if units]
                first, end = nonzero[0], nonzero[-1] + 1
                completion = start + end * duration
                for gun in range(2):
                    plans = options[vehicle["id"]]
                    if len(plans) >= max_options_per_vehicle:
                        raise ValueError("Too many candidate plans; shorten the horizon, coarsen the grid, "
                                         "or explicitly increase max_options_per_vehicle")
                    plans.append({
                        "vehicle_id": vehicle["id"], "module_id": module["id"], "gun": gun,
                        "start_slot": first, "end_slot": end,
                        "start_minute": start + first * duration, "completion_minute": completion,
                        "power_kw_by_slot": tuple(units * step for units in full_profile),
                        "charging_energy_kwh": vehicle["required_energy_kwh"],
                        "waiting_minutes": start + first * duration - vehicle["arrival_minute"],
                        "flow_minutes": completion - vehicle["arrival_minute"],
                        "score": completion - vehicle["arrival_minute"],
                    })
    return options


def _conflict(first, second, module_power):
    if first["module_id"] != second["module_id"]:
        return False
    overlap = max(first["start_slot"], second["start_slot"]) < min(first["end_slot"], second["end_slot"])
    if first["gun"] == second["gun"] and overlap:
        return True
    return any(a + b > module_power[first["module_id"]] + TOLERANCE
               for a, b in zip(first["power_kw_by_slot"], second["power_kw_by_slot"]))


def build_shared_power_qubo(scenario, *, penalty=None, max_options_per_vehicle=1000):
    """Return coefficients compatible with quantum_scheduler.qubo_to_ising.

    F(x) = sum(c[p]*x[p]) + P*sum_i(sum_{p in plans[i]} x[p] - 1)^2
           + P*sum_{(p,q) incompatible, different cars} x[p]*x[q].

    c[p] is arrival-to-completion time in minutes. Minimizing its sum minimizes
    its average because all vehicles must be served. No tariff is included.
    """
    options = generate_shared_power_options(scenario, max_options_per_vehicle=max_options_per_vehicle)
    missing = [vehicle_id for vehicle_id, plans in options.items() if not plans]
    if missing:
        raise ValueError(f"No grid-feasible charging plan for: {', '.join(missing)}")
    score_bound = sum(max(p["score"] for p in plans) for plans in options.values())
    if penalty is None:
        penalty = score_bound + 1.0
    _number(penalty, "penalty", positive=True)
    # A low custom penalty would invalidate the feasibility guarantee.
    if penalty <= score_bound:
        raise ValueError(f"penalty must exceed the safe score bound {score_bound:g}")
    variables, groups = [], {}
    for vehicle_id, plans in options.items():
        groups[vehicle_id] = list(range(len(variables), len(variables) + len(plans)))
        variables.extend(plans)
    quadratic = {}
    for indices in groups.values():
        for i, j in combinations(indices, 2):
            quadratic[i, j] = 2 * penalty
    module_power = {m["id"]: m["power_kw"] for m in scenario["modules"]}
    conflicts = []
    for i, j in combinations(range(len(variables)), 2):
        if variables[i]["vehicle_id"] != variables[j]["vehicle_id"] and _conflict(variables[i], variables[j], module_power):
            conflicts.append((i, j))
            quadratic[i, j] = penalty
    return {
        "kind": "shared_power", "scenario": deepcopy(scenario),
        "variables": variables, "groups": groups, "conflicts": conflicts,
        "score_bound": score_bound, "penalty": float(penalty),
        "constant": float(penalty * len(groups)),
        "linear": [p["score"] - penalty for p in variables], "quadratic": quadratic,
        "objective": "total_flow_minutes", "objective_units": "minutes",
    }


def decode_shared_power_bits(model, bits):
    """Validate actual energy, power, occupancy and deadlines, not QUBO edges."""
    if len(bits) != len(model["variables"]) or any(bit not in (0, 1) for bit in bits):
        raise ValueError("Provide one binary value per candidate plan, in qubit order")
    reasons = [f"{vehicle_id} needs exactly one charging plan"
               for vehicle_id, indices in model["groups"].items() if sum(bits[i] for i in indices) != 1]
    scenario = model["scenario"]
    modules = {m["id"]: m for m in scenario["modules"]}
    vehicles = {v["id"]: v for v in scenario["vehicles"]}
    schedule = [plan for bit, plan in zip(bits, model["variables"]) if bit]
    occupied, power = {}, {}
    for plan in schedule:
        vehicle = vehicles[plan["vehicle_id"]]
        profile = plan["power_kw_by_slot"]
        energy = sum(profile) * scenario["slot_minutes"] / 60
        if not isclose(energy, vehicle["required_energy_kwh"], rel_tol=0, abs_tol=TOLERANCE):
            reasons.append(f"{vehicle['id']} has incorrect delivered energy")
        if any(p < 0 or p > vehicle["max_power_kw"] + TOLERANCE for p in profile):
            reasons.append(f"{vehicle['id']} exceeds its vehicle power limit")
        if plan["start_minute"] < vehicle["arrival_minute"] or plan["completion_minute"] > vehicle["deadline_minute"]:
            reasons.append(f"{vehicle['id']} violates arrival/deadline")
        for t in range(plan["start_slot"], plan["end_slot"]):
            key = (plan["module_id"], plan["gun"], t)
            if key in occupied:
                reasons.append(f"Gun conflict at {key[0]} / gun {key[1]} / slot {t}")
            occupied[key] = vehicle["id"]
        for t, kw in enumerate(profile):
            key = (plan["module_id"], t)
            power[key] = power.get(key, 0) + kw
    for (module_id, t), kw in power.items():
        if kw > modules[module_id]["power_kw"] + TOLERANCE:
            reasons.append(f"Shared power exceeded at {module_id} / slot {t}: {kw:g} kW")
    return {"valid": not reasons, "reasons": reasons, "schedule": schedule}


def shared_power_metrics(model, schedule):
    """Compute time metrics for an already validated complete schedule."""
    total = sum(plan["flow_minutes"] for plan in schedule)
    return {
        "total_flow_minutes": total, "average_flow_minutes": total / len(model["groups"]),
        "total_waiting_minutes": sum(plan["waiting_minutes"] for plan in schedule),
        "last_completion_minute": max(plan["completion_minute"] for plan in schedule),
        "total_score": total,
    }


def solve_shared_power_exact(model, *, max_combinations=1_000_000):
    """Explicit classical reference, never a fallback inside quantum execution.

    Enumerate one plan per vehicle, not all 2**n bitstrings. This is still
    exponential and is intended only to verify small educational instances.
    """
    _integer(max_combinations, "max_combinations", positive=True)
    size = prod(len(indices) for indices in model["groups"].values())
    if size > max_combinations:
        raise ValueError(f"Exact reference needs {size} combinations; limit is {max_combinations}")
    best, best_bits = None, None
    for chosen in product(*model["groups"].values()):
        bits = [0] * len(model["variables"])
        for i in chosen:
            bits[i] = 1
        decoded = decode_shared_power_bits(model, bits)
        if decoded["valid"] and (best is None or sum(p["score"] for p in decoded["schedule"]) < best["total_score"]):
            best = {"schedule": decoded["schedule"], **shared_power_metrics(model, decoded["schedule"])}
            best_bits = bits
    if best is None:
        return {"status": "infeasible", "schedule": [], "bits": None, "total_score": None,
                "combinations_checked": size}
    return {"status": "optimal", "bits": best_bits, "combinations_checked": size, **best}
