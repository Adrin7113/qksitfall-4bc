"""Generate EV charging bookings and find the best small schedule.

All inputs and outputs are ordinary dictionaries. Time is measured in minutes
from midnight, energy in kWh, power in kW, and electricity prices in rupees/kWh.
"""

from itertools import product
from math import isfinite


EPSILON = 1e-9


def _require_keys(value, keys, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dictionary")
    for key in keys:
        if key not in value:
            raise ValueError(f"{label} is missing {key!r}")


def _number(value, label, minimum=0, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    if not isfinite(value) or value < minimum or (positive and value == 0):
        comparison = "greater than" if positive else "at least"
        raise ValueError(f"{label} must be finite and {comparison} {minimum}")


def _minute(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1440:
        raise ValueError(f"{label} must be an integer from 0 to 1440")


def _records(records, label):
    if not isinstance(records, list) or not records:
        raise ValueError(f"{label} must be a nonempty list")
    ids = []
    for record in records:
        _require_keys(record, ("id",), label)
        record_id = record["id"]
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError(f"{label} IDs must be nonempty strings")
        if record_id in ids:
            raise ValueError(f"{label} contains duplicate ID {record_id!r}")
        ids.append(record_id)
    return ids


def validate_scenario(scenario):
    """Raise ValueError for malformed inputs; infeasible inputs are still valid."""
    _require_keys(scenario, ("vehicles", "stations", "slots", "travel"), "scenario")
    vehicle_ids = _records(scenario["vehicles"], "vehicles")
    station_ids = _records(scenario["stations"], "stations")
    slot_ids = _records(scenario["slots"], "slots")

    reserve = scenario.get("reserve_percent", 5)
    _number(reserve, "reserve_percent")
    if reserve > 100:
        raise ValueError("reserve_percent must not exceed 100")
    _number(scenario.get("waiting_weight_per_minute", 0.25), "waiting_weight_per_minute")

    for vehicle in scenario["vehicles"]:
        label = f"vehicle {vehicle['id']}"
        _require_keys(vehicle, (
            "battery_capacity_kwh", "current_charge_percent", "target_charge_percent",
            "consumption_kwh_per_km", "available_from_minute", "deadline_minute",
        ), label)
        _number(vehicle["battery_capacity_kwh"], f"{label} battery capacity", positive=True)
        _number(vehicle["consumption_kwh_per_km"], f"{label} consumption", positive=True)
        current = vehicle["current_charge_percent"]
        target = vehicle["target_charge_percent"]
        _number(current, f"{label} current charge")
        _number(target, f"{label} target charge")
        if not 0 <= current < target <= 100:
            raise ValueError(f"{label} requires 0 <= current charge < target charge <= 100")
        _minute(vehicle["available_from_minute"], f"{label} availability")
        _minute(vehicle["deadline_minute"], f"{label} deadline")
        if vehicle["available_from_minute"] >= vehicle["deadline_minute"]:
            raise ValueError(f"{label} availability must precede its deadline")

    for slot in scenario["slots"]:
        _require_keys(slot, ("start_minute", "end_minute"), f"slot {slot['id']}")
        _minute(slot["start_minute"], "slot start")
        _minute(slot["end_minute"], "slot end")
        if slot["end_minute"] - slot["start_minute"] != 60:
            raise ValueError("Every slot must last exactly 60 minutes")
    chronological_slots = sorted(scenario["slots"], key=lambda slot: slot["start_minute"])
    for previous, following in zip(chronological_slots, chronological_slots[1:]):
        if previous["end_minute"] > following["start_minute"]:
            raise ValueError("Slots must not overlap")

    for station in scenario["stations"]:
        label = f"station {station['id']}"
        _require_keys(station, ("power_kw", "prices_per_kwh"), label)
        _number(station["power_kw"], f"{label} power", positive=True)
        _require_keys(station["prices_per_kwh"], slot_ids, f"{label} prices_per_kwh")
        for slot_id in slot_ids:
            _number(station["prices_per_kwh"][slot_id], f"{label} price for {slot_id}")

    travel = scenario["travel"]
    _require_keys(travel, vehicle_ids, "travel")
    if set(travel) != set(vehicle_ids):
        raise ValueError("travel must contain exactly the vehicle IDs")
    for vehicle_id in vehicle_ids:
        _require_keys(travel[vehicle_id], station_ids, f"travel for {vehicle_id}")
        if set(travel[vehicle_id]) != set(station_ids):
            raise ValueError(f"travel for {vehicle_id} must contain exactly the station IDs")
        for station_id in station_ids:
            journey = travel[vehicle_id][station_id]
            label = f"travel {vehicle_id} -> {station_id}"
            _require_keys(journey, ("distance_km", "duration_minutes"), label)
            _number(journey["distance_km"], f"{label} distance")
            _minute(journey["duration_minutes"], f"{label} duration")


def calculate_journey(vehicle, travel):
    """Calculate one journey, assuming scenario validation has already passed.

    Driving reduces the arrival battery level, so a farther station can require
    more charging energy even when the driver's target percentage is unchanged.
    """
    capacity = vehicle["battery_capacity_kwh"]
    initial_energy = capacity * vehicle["current_charge_percent"] / 100
    driving_energy = travel["distance_km"] * vehicle["consumption_kwh_per_km"]
    arrival_energy = initial_energy - driving_energy
    target_energy = capacity * vehicle["target_charge_percent"] / 100

    return {
        "initial_energy_kwh": initial_energy,
        "driving_energy_kwh": driving_energy,
        "arrival_energy_kwh": arrival_energy,
        "arrival_minute": vehicle["available_from_minute"] + travel["duration_minutes"],
        "target_energy_kwh": target_energy,
        "charging_energy_kwh": target_energy - arrival_energy,
    }


def generate_options(scenario):
    """Return {'options': {vehicle_id: [booking, ...]}, 'rejected': [...]}.

    This checks one car at a time. Two individually feasible bookings may still
    conflict with each other; choosing a compatible combination is a later step.
    Input order is preserved so solver tie-breaking can be deterministic.
    """
    validate_scenario(scenario)
    options = {vehicle["id"]: [] for vehicle in scenario["vehicles"]}
    rejected = []
    reserve_percent = scenario.get("reserve_percent", 5)
    waiting_weight = scenario.get("waiting_weight_per_minute", 0.25)

    for vehicle in scenario["vehicles"]:
        vehicle_id = vehicle["id"]
        reserve_energy = vehicle["battery_capacity_kwh"] * reserve_percent / 100

        for station in scenario["stations"]:
            station_id = station["id"]
            travel = scenario["travel"][vehicle_id][station_id]
            journey = calculate_journey(vehicle, travel)
            charging_duration = journey["charging_energy_kwh"] / station["power_kw"] * 60

            for slot in scenario["slots"]:
                # Each rejected combination explains all of its broken rules.
                reasons = []
                if journey["arrival_energy_kwh"] + EPSILON < reserve_energy:
                    reasons.append("Arrival battery would be below the required reserve")
                if journey["arrival_minute"] > slot["start_minute"]:
                    reasons.append("Arrival is after the slot starts")

                completion = slot["start_minute"] + charging_duration
                if completion > vehicle["deadline_minute"] + EPSILON:
                    reasons.append("Charging would finish after the vehicle deadline")

                slot_hours = (slot["end_minute"] - slot["start_minute"]) / 60
                energy_available = station["power_kw"] * slot_hours
                if journey["charging_energy_kwh"] > energy_available + EPSILON:
                    reasons.append("Charger cannot deliver the required energy within this slot")

                if reasons:
                    rejected.append({
                        "vehicle_id": vehicle_id,
                        "station_id": station_id,
                        "slot_id": slot["id"],
                        "reasons": reasons,
                    })
                    continue

                waiting_minutes = slot["start_minute"] - journey["arrival_minute"]
                electricity_cost = (
                    journey["charging_energy_kwh"] * station["prices_per_kwh"][slot["id"]]
                )
                score = electricity_cost + waiting_weight * waiting_minutes

                options[vehicle_id].append({
                    "vehicle_id": vehicle_id,
                    "station_id": station_id,
                    "slot_id": slot["id"],
                    "start_minute": slot["start_minute"],
                    "end_minute": slot["end_minute"],
                    **journey,
                    "charging_duration_minutes": charging_duration,
                    "completion_minute": completion,
                    "waiting_minutes": waiting_minutes,
                    "electricity_cost_rupees": electricity_cost,
                    "score": score,
                })

    return {"options": options, "rejected": rejected}


def solve_exact(scenario, options):
    """Find the cheapest conflict-free combination of generated bookings.

    Pass the unmodified `generate_options(scenario)['options']` mapping for this
    scenario. This is exhaustive search for small examples, not a quantum solver.
    Each car receives one booking; each station has one port. Slots were checked
    for overlap during validation, so (station_id, slot_id) identifies a resource.
    """
    validate_scenario(scenario)
    vehicle_ids = [vehicle["id"] for vehicle in scenario["vehicles"]]
    _require_keys(options, vehicle_ids, "options")
    if set(options) != set(vehicle_ids):
        raise ValueError("options must contain exactly the vehicle IDs")

    result = {
        "status": "infeasible",
        "reason": None,
        "schedule": [],
        "total_electricity_cost_rupees": None,
        "total_waiting_minutes": None,
        "total_charging_energy_kwh": None,
        "total_score": None,
        "combinations_checked": 0,
        "feasible_combinations": 0,
    }
    missing = [vehicle_id for vehicle_id in vehicle_ids if not options[vehicle_id]]
    if missing:
        result["reason"] = f"No feasible booking for: {', '.join(missing)}"
        return result

    best_combination = None
    best_score = float("inf")
    choices = [options[vehicle_id] for vehicle_id in vehicle_ids]

    # product([A's options], [B's options], ...) chooses one option per car.
    for combination in product(*choices):
        result["combinations_checked"] += 1
        occupied = set()
        conflict = False

        for booking in combination:
            resource = (booking["station_id"], booking["slot_id"])
            if resource in occupied:
                conflict = True
                break
            occupied.add(resource)

        if conflict:
            continue

        result["feasible_combinations"] += 1
        total_score = sum(booking["score"] for booking in combination)
        # Strict improvement keeps the first combination when scores are equal.
        if total_score < best_score:
            best_score = total_score
            best_combination = combination

    if best_combination is None:
        result["reason"] = "Every combination has a station/slot conflict"
        return result

    result.update({
        "status": "optimal",
        "schedule": list(best_combination),
        "total_electricity_cost_rupees": sum(
            booking["electricity_cost_rupees"] for booking in best_combination
        ),
        "total_waiting_minutes": sum(booking["waiting_minutes"] for booking in best_combination),
        "total_charging_energy_kwh": sum(
            booking["charging_energy_kwh"] for booking in best_combination
        ),
        "total_score": best_score,
    })
    return result
