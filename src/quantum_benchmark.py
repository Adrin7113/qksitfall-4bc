"""Reproducible small-instance comparison of the unchanged scheduling solvers.

All runtime measurements are local CPU measurements, including Aer simulation.
The physical validator below recomputes rules from power profiles; it does not
use QUBO conflict edges or the quantum solver's decoded validity flags.
"""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from math import isclose, isfinite, prod
from pathlib import Path
import platform
from random import Random
from statistics import median
from time import perf_counter, process_time

import numpy as np
import qiskit
import qiskit_aer
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp

from shared_power_demo import sample_shared_power_scenario
from src.shared_power_scheduler import (
    build_shared_power_qubo, generate_shared_power_options, solve_shared_power_exact,
)
from src.quantum_scheduler import solve_qaoa


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "src/quantum_benchmark.py", "scripts/benchmark_quantum.py",
    "src/quantum_scheduler.py", "src/shared_power_scheduler.py", "shared_power_demo.py",
)
QAOA_CONFIG = {"layers": 2, "iterations": 80, "restarts": 2, "shots": 2048}
METHODS = ("qaoa", "milp", "structured_random")
TOL = 1e-8


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_hashes(root=ROOT):
    return {name: sha256((Path(root) / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def benchmark_cases():
    base = sample_shared_power_scenario()
    cases = [
        {"id": "original", "label": "Two cars · shared 50 kW module", "scenario": deepcopy(base)},
        {"id": "urgent", "label": "B must finish by minute 30", "scenario": deepcopy(base)},
        {"id": "late", "label": "B arrives at minute 30", "scenario": deepcopy(base)},
        {"id": "three_cars", "label": "Three cars · shared 50 kW module", "scenario": deepcopy(base)},
        {"id": "two_modules", "label": "Two independent 50 kW modules", "scenario": deepcopy(base)},
    ]
    cases[1]["scenario"]["vehicles"][1]["deadline_minute"] = 30
    cases[2]["scenario"]["vehicles"][1]["arrival_minute"] = 30
    cases[3]["scenario"]["vehicles"] = [
        {"id": name, "required_energy_kwh": 12.5, "max_power_kw": 25,
         "arrival_minute": 0, "deadline_minute": 60} for name in "ABC"
    ]
    two = cases[4]["scenario"]
    two["num_slots"] = 1
    two["modules"].append({"id": "M2", "power_kw": 50, "gun_count": 2})
    two["vehicles"][0]["required_energy_kwh"] = 25
    for vehicle in two["vehicles"]:
        vehicle["deadline_minute"] = 30
    return cases


def candidate_view(scenario):
    """Classical/MILP inputs: plans and groups only, without QUBO penalties."""
    options = generate_shared_power_options(scenario)
    plans, groups = [], {}
    for vehicle_id, choices in options.items():
        if not choices:
            raise ValueError(f"No candidate plans for {vehicle_id}")
        groups[vehicle_id] = list(range(len(plans), len(plans) + len(choices)))
        plans.extend(choices)
    return {"scenario": scenario, "variables": plans, "groups": groups}


def validate_selection(scenario, plans):
    """Return physical metrics only after independently checking the schedule."""
    vehicles = {v["id"]: v for v in scenario["vehicles"]}
    modules = {m["id"]: m for m in scenario["modules"]}
    if any(sum(p["vehicle_id"] == name for p in plans) != 1 for name in vehicles):
        return {"valid": False}
    power = {name: [0] * scenario["num_slots"] for name in modules}
    occupied, flow, completions = set(), 0, []
    for plan in plans:
        if plan["vehicle_id"] not in vehicles or plan["module_id"] not in modules or plan["gun"] not in (0, 1):
            return {"valid": False}
        vehicle = vehicles[plan["vehicle_id"]]
        profile = plan["power_kw_by_slot"]
        if len(profile) != scenario["num_slots"] or any(not isfinite(p) or p < 0 or p > vehicle["max_power_kw"] + TOL for p in profile):
            return {"valid": False}
        energy = sum(profile) * scenario["slot_minutes"] / 60
        if not isclose(energy, vehicle["required_energy_kwh"], rel_tol=0, abs_tol=TOL):
            return {"valid": False}
        active = [t for t, kw in enumerate(profile) if kw > 0]
        if not active:
            return {"valid": False}
        first, end = active[0], active[-1] + 1
        start = scenario["start_minute"] + first * scenario["slot_minutes"]
        completion = scenario["start_minute"] + end * scenario["slot_minutes"]
        if start < vehicle["arrival_minute"] or completion > vehicle["deadline_minute"]:
            return {"valid": False}
        for t in range(first, end):
            key = (plan["module_id"], plan["gun"], t)
            if key in occupied:
                return {"valid": False}
            occupied.add(key)
        for t, kw in enumerate(profile):
            power[plan["module_id"]][t] += kw
        flow += completion - vehicle["arrival_minute"]
        completions.append(completion)
    if any(kw > modules[name]["power_kw"] + TOL for name, profile in power.items() for kw in profile):
        return {"valid": False}
    return {"valid": True, "total_flow_minutes": flow,
            "average_flow_minutes": flow / len(vehicles), "last_completion_minute": max(completions)}


def native_milp_constraints(view):
    """Explicit assignment, module power and gun occupancy; no QUBO terms."""
    plans, scenario = view["variables"], view["scenario"]
    rows, lower, upper = [], [], []
    for indices in view["groups"].values():
        row = np.zeros(len(plans)); row[indices] = 1
        rows.append(row); lower.append(1); upper.append(1)
    for module in scenario["modules"]:
        for t in range(scenario["num_slots"]):
            rows.append([p["power_kw_by_slot"][t] if p["module_id"] == module["id"] else 0 for p in plans])
            lower.append(-np.inf); upper.append(module["power_kw"])
            for gun in range(2):
                rows.append([int(p["module_id"] == module["id"] and p["gun"] == gun
                                 and p["start_slot"] <= t < p["end_slot"]) for p in plans])
                lower.append(-np.inf); upper.append(1)
    return LinearConstraint(np.asarray(rows), np.asarray(lower), np.asarray(upper))


def analyze_counts(view, counts, optimum):
    """Counts use Qiskit's displayed order, with the highest qubit first."""
    valid_samples = optimal_samples = 0
    best, best_bits = None, None
    for string, count in counts.items():
        if len(string) != len(view["variables"]) or any(c not in "01" for c in string) or count < 1:
            raise ValueError("Malformed sampled bitstring/count")
        bits = [int(c) for c in reversed(string)]
        selected = [p for bit, p in zip(bits, view["variables"]) if bit]
        metrics = validate_selection(view["scenario"], selected)
        if metrics["valid"]:
            valid_samples += count
            if isclose(metrics["total_flow_minutes"], optimum, rel_tol=0, abs_tol=TOL):
                optimal_samples += count
            if best is None or metrics["total_flow_minutes"] < best["total_flow_minutes"]:
                best, best_bits = metrics, bits
    return {"best": best, "bits": best_bits, "valid_samples": valid_samples, "optimal_samples": optimal_samples}


def run_trial(scenario, method, seed, optimum, config=None):
    config = dict(QAOA_CONFIG if config is None else config)
    started = perf_counter()
    cpu_started = process_time()
    if method not in METHODS:
        raise ValueError(f"Unknown benchmark method: {method}")
    record = {"method": method, "seed": seed, "status": "error", "valid_answer": False,
              "hit_optimum": False, "best_total_flow_minutes": None, "best_average_flow_minutes": None,
              "relative_optimality_gap": None, "feasible_sample_fraction": None,
              "optimal_sample_fraction": None, "sample_count": None, "bits": None}
    try:
        view = build_shared_power_qubo(scenario) if method == "qaoa" else candidate_view(scenario)
        constraints = native_milp_constraints(view) if method == "milp" else None
        record["plan_fingerprint"] = fingerprint(view["variables"])
        prepared = perf_counter()
        cpu_prepared = process_time()
        if method == "qaoa":
            result = solve_qaoa(view, seed=seed, **config)
            counts = result["counts"]
            record["training_evaluations"] = len(result["history"])
            if sum(counts.values()) != config["shots"]:
                raise ValueError("QAOA measurement count does not match its shot budget")
        elif method == "milp":
            result = milp(np.asarray([p["score"] for p in view["variables"]]),
                          integrality=np.ones(len(view["variables"])), bounds=Bounds(0, 1),
                          constraints=constraints, options={"mip_rel_gap": 0.0})
            record.update(solver_status=int(result.status), solver_message=str(result.message))
        else:
            rng = Random(seed)
            counts = Counter()
            for _ in range(config["shots"]):
                bits = [0] * len(view["variables"])
                for indices in view["groups"].values():
                    bits[rng.choice(indices)] = 1
                counts["".join(map(str, reversed(bits)))] += 1
        solved = perf_counter()
        cpu_solved = process_time()
        if method == "milp":
            best, bits = None, None
            if result.x is not None:
                bits = np.rint(result.x).astype(int).tolist()
                best = validate_selection(scenario, [p for p, bit in zip(view["variables"], bits) if bit])
                if not best["valid"]:
                    raise ValueError("MILP returned a physically invalid schedule")
                if result.status == 0 and not isclose(best["total_flow_minutes"], optimum, rel_tol=0, abs_tol=TOL):
                    raise ValueError("MILP optimum disagrees with the independent exact reference")
        else:
            analyzed = analyze_counts(view, counts, optimum)
            best, bits = analyzed["best"], analyzed["bits"]
            record.update(sample_counts=dict(counts), sample_count=sum(counts.values()),
                          valid_samples=analyzed["valid_samples"], optimal_samples=analyzed["optimal_samples"],
                          feasible_sample_fraction=analyzed["valid_samples"] / sum(counts.values()),
                          optimal_sample_fraction=analyzed["optimal_samples"] / sum(counts.values()))
            if method == "qaoa" and (bool(best) != (result["status"] == "feasible")
                                      or analyzed["valid_samples"] != result["valid_shots"]
                                      or best and not isclose(best["total_flow_minutes"], result["total_score"], rel_tol=0, abs_tol=TOL)):
                raise ValueError("Independent physical checks disagree with QAOA decoding")
        validated = perf_counter()
        cpu_validated = process_time()
        record.update(status="feasible" if best else "no_feasible_answer", valid_answer=bool(best), bits=bits,
                      timings={"prepare_seconds": prepared - started, "solve_seconds": solved - prepared,
                               "validation_seconds": validated - solved, "total_seconds": validated - started,
                               "prepare_cpu_seconds": cpu_prepared - cpu_started, "solve_cpu_seconds": cpu_solved - cpu_prepared,
                               "validation_cpu_seconds": cpu_validated - cpu_solved, "total_cpu_seconds": cpu_validated - cpu_started})
        if best:
            score = best["total_flow_minutes"]
            if score < optimum - TOL:
                raise ValueError("A returned schedule beats the exact reference; benchmark invariant failed")
            record.update(best_total_flow_minutes=score, best_average_flow_minutes=best["average_flow_minutes"],
                          hit_optimum=isclose(score, optimum, rel_tol=0, abs_tol=TOL),
                          relative_optimality_gap=max(0.0, (score - optimum) / optimum))
    except Exception as error:
        record.update(status="error", valid_answer=False, hit_optimum=False,
                      best_total_flow_minutes=None, best_average_flow_minutes=None,
                      relative_optimality_gap=None, bits=None,
                      error={"type": type(error).__name__, "message": str(error)},
                      timings={"total_seconds": perf_counter() - started, "total_cpu_seconds": process_time() - cpu_started})
    return record


def summarize_runs(runs):
    summary = {}
    for method in METHODS:
        rows = [r for r in runs if r["method"] == method]
        successful = [r for r in rows if r["valid_answer"]]
        fractions = [r["feasible_sample_fraction"] for r in rows if r["status"] != "error" and r["feasible_sample_fraction"] is not None]
        summary[method] = {
            "runs": len(rows), "valid_answers": len(successful), "optimal_answers": sum(r["hit_optimum"] for r in rows),
            "errors": sum(r["status"] == "error" for r in rows),
            "median_average_minutes": median(r["best_average_flow_minutes"] for r in successful) if successful else None,
            "median_relative_gap": median(r["relative_optimality_gap"] for r in successful) if successful else None,
            "median_total_seconds": median(r["timings"]["total_seconds"] for r in rows),
            "median_cpu_seconds": median(r["timings"]["total_cpu_seconds"] for r in rows),
            "median_feasible_sample_fraction": median(fractions) if fractions else None,
        }
    return summary


def run_benchmark(seeds=range(10), config=None, progress=None):
    seeds, config = list(seeds), dict(QAOA_CONFIG if config is None else config)
    if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Provide distinct nonnegative integer seeds")
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": "total_flow_minutes", "scope": "shared-power scheduling on a discrete grid",
        "config": {"seeds": seeds, "qaoa": config, "structured_random_draws": config["shots"],
                   "milp": "SciPy/HiGHS, native assignment/power/occupancy constraints, zero MIP relative gap"},
        "environment": {"python": platform.python_version(), "os": platform.system(), "architecture": platform.machine(),
                        "numpy": np.__version__, "scipy": scipy.__version__, "qiskit": qiskit.__version__, "qiskit_aer": qiskit_aer.__version__},
        "timing_policy": "Process CPU time and elapsed wall time per workflow, including candidate generation, formulation, solving/training/sampling, and independent validation. Interpreter/library imports and exact-reference computation are excluded. CPU time sums process threads and can exceed wall time. Aer measurements are simulation runtime, not QPU runtime. No quantum hardware was used.",
        "thread_policy": "Existing Aer solver uses one thread; HiGHS uses its defaults. No CPU affinity or resource isolation is enforced.",
        "sample_policy": "QAOA and structured random use the same final sample count, not equal computational work. MILP is not a sampler. Counts are stored in Qiskit displayed bit order (highest qubit first).",
        "source_hashes": source_hashes(), "cases": [],
    }
    for case in benchmark_cases():
        model = build_shared_power_qubo(case["scenario"])
        reference = solve_shared_power_exact(model)
        if reference["status"] != "optimal" or not validate_selection(case["scenario"], reference["schedule"])["valid"]:
            raise ValueError(f"Invalid benchmark reference: {case['id']}")
        total_choices = prod(len(indices) for indices in model["groups"].values())
        feasible_choices = sum(validate_selection(case["scenario"], [model["variables"][i] for i in chosen])["valid"]
                               for chosen in product(*model["groups"].values()))
        record = {**case, "qubits": len(model["variables"]), "plans": model["variables"],
                  "plan_fingerprint": fingerprint(model["variables"]),
                  "reference": {"total_flow_minutes": reference["total_score"], "average_flow_minutes": reference["average_flow_minutes"]},
                  "analytical_reference": {"kind": "exact counting, not a sampled optimizer",
                                           "feasible_choices": feasible_choices, "one_plan_per_car_choices": total_choices,
                                           "encoded_bitstrings": 2 ** len(model["variables"]),
                                           "uniform_bitstring_feasibility": feasible_choices / 2 ** len(model["variables"]),
                                           "structured_uniform_feasibility": feasible_choices / total_choices}, "runs": []}
        for index, seed in enumerate(seeds):
            order = METHODS[index % 3:] + METHODS[:index % 3]
            for method in order:
                run = run_trial(case["scenario"], method, seed, reference["total_score"], config)
                if run.get("plan_fingerprint", record["plan_fingerprint"]) != record["plan_fingerprint"]:
                    raise ValueError("Methods received different candidate plans")
                record["runs"].append(run)
            if progress:
                progress(case["id"], seed, record["runs"][-3:])
        record["summary"] = summarize_runs(record["runs"])
        report["cases"].append(record)
    return report


def validate_report(report, root=ROOT, *, require_full_protocol=True):
    """Release gate: reject stale code, mismatched cases, and incorrect metrics."""
    if report.get("schema_version") != 1 or report.get("source_hashes") != source_hashes(root):
        raise ValueError("Stale benchmark report: rerun scripts/benchmark_quantum.py")
    if require_full_protocol and (report.get("config", {}).get("seeds") != list(range(10))
                                  or report["config"].get("qaoa") != QAOA_CONFIG
                                  or report["config"].get("structured_random_draws") != QAOA_CONFIG["shots"]):
        raise ValueError("Report does not use the approved full benchmark protocol")
    expected = benchmark_cases()
    if [c["id"] for c in report.get("cases", [])] != [c["id"] for c in expected]:
        raise ValueError("Benchmark cases do not match the protocol")
    for case, definition in zip(report["cases"], expected):
        model = build_shared_power_qubo(definition["scenario"])
        exact = solve_shared_power_exact(model)
        if (case["scenario"] != definition["scenario"] or fingerprint(model["variables"]) != case["plan_fingerprint"]
                or fingerprint(case["plans"]) != case["plan_fingerprint"]):
            raise ValueError("Benchmark inputs/plans do not match current inputs")
        if exact["total_score"] != case["reference"]["total_flow_minutes"] or len(model["variables"]) != case["qubits"]:
            raise ValueError("Benchmark reference mismatch")
        a = case["analytical_reference"]
        combinations = prod(len(indices) for indices in model["groups"].values())
        feasible = sum(validate_selection(case["scenario"], [model["variables"][i] for i in chosen])["valid"]
                       for chosen in product(*model["groups"].values()))
        if (a["feasible_choices"] != feasible or a["one_plan_per_car_choices"] != combinations
                or a["encoded_bitstrings"] != 2 ** case["qubits"]
                or a["uniform_bitstring_feasibility"] != feasible / 2 ** case["qubits"]
                or a["structured_uniform_feasibility"] != feasible / combinations):
            raise ValueError("Incorrect analytical reference")
        if case["summary"] != summarize_runs(case["runs"]):
            raise ValueError("Incorrect benchmark aggregates")
        for method in METHODS:
            if sorted(r["seed"] for r in case["runs"] if r["method"] == method) != sorted(report["config"]["seeds"]):
                raise ValueError("Missing or duplicate benchmark trials")
        for run in case["runs"]:
            if run["method"] not in METHODS or run["status"] not in ("feasible", "no_feasible_answer", "error"):
                raise ValueError("Unknown benchmark method/status")
            if run["status"] == "error":
                if run["valid_answer"] or run["hit_optimum"] or run["bits"] is not None or run["best_total_flow_minutes"] is not None:
                    raise ValueError("Error run must not contain a successful answer")
                continue  # Failures are retained and visibly counted, not fabricated.
            if run["plan_fingerprint"] != case["plan_fingerprint"]:
                raise ValueError("Run used different candidate plans")
            if run["valid_answer"] != (run["bits"] is not None) or run["valid_answer"] != (run["status"] == "feasible"):
                raise ValueError("Answer status/bit vector mismatch")
            if run["bits"] is not None:
                if len(run["bits"]) != case["qubits"] or any(bit not in (0, 1) for bit in run["bits"]):
                    raise ValueError("Invalid answer bit vector")
                metrics = validate_selection(case["scenario"], [p for bit, p in zip(run["bits"], case["plans"]) if bit])
                if not metrics["valid"] or metrics["total_flow_minutes"] != run["best_total_flow_minutes"]:
                    raise ValueError("Invalid recorded answer")
            if run["method"] != "milp":
                a = analyze_counts(model, run["sample_counts"], exact["total_score"])
                expected_samples = report["config"]["qaoa"]["shots"] if run["method"] == "qaoa" else report["config"]["structured_random_draws"]
                if run["sample_count"] != expected_samples:
                    raise ValueError("Recorded sample budget mismatch")
                if sum(run["sample_counts"].values()) != run["sample_count"] or a["valid_samples"] != run["valid_samples"]:
                    raise ValueError("Incorrect recorded sample counts")
                if run["feasible_sample_fraction"] != a["valid_samples"] / run["sample_count"]:
                    raise ValueError("Incorrect sample fraction")
                if (a["optimal_samples"] != run["optimal_samples"]
                        or run["optimal_sample_fraction"] != a["optimal_samples"] / run["sample_count"]
                        or bool(a["best"]) != run["valid_answer"]):
                    raise ValueError("Incorrect optimal/valid sample metrics")
                if run["valid_answer"] and (a["best"]["total_flow_minutes"] != run["best_total_flow_minutes"]
                        or run["sample_counts"].get("".join(map(str, reversed(run["bits"]))), 0) < 1):
                    raise ValueError("Recorded answer is not a best observed sample")
            if run["valid_answer"]:
                score = run["best_total_flow_minutes"]
                if (run["best_average_flow_minutes"] != score / len(case["scenario"]["vehicles"])
                        or run["hit_optimum"] != isclose(score, exact["total_score"], rel_tol=0, abs_tol=TOL)
                        or not isclose(run["relative_optimality_gap"], (score - exact["total_score"]) / exact["total_score"], rel_tol=0, abs_tol=TOL)):
                    raise ValueError("Incorrect solution-quality metrics")
            elif any(run[key] is not None for key in ("best_total_flow_minutes", "best_average_flow_minutes", "relative_optimality_gap")) or run["hit_optimum"]:
                raise ValueError("Failed run must not contain solution-quality metrics")
            if any(not isfinite(t) or t < 0 for t in run["timings"].values()):
                raise ValueError("Invalid recorded runtime")
    return True
