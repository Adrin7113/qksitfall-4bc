# Quantum contribution and benchmark protocol

The contribution is a charging-specific encoding and a validated hybrid workflow using standard QAOA. Complete charging plans become binary variables; exactly-one and physical compatibility penalties become an Ising Hamiltonian. The existing circuit alternates cost rotations and an X mixer; COBYLA tunes four angles. This is an application of QAOA, not a new quantum algorithm.

The five cases use the same physical assumptions as the shared-power scheduler: fixed vehicle ceilings, exact requested energy on a discrete time/power grid, two guns per module, retained gun occupancy during internal pauses, and independent module budgets. There are no charging curves or hardware controller measurements. Station booking remains a separate unchanged example.

## Reproduce

From the project root, with the existing virtual environment:

```sh
.venv/bin/python scripts/benchmark_quantum.py
.venv/bin/python -m unittest discover -s tests -q
```

The CLI atomically writes `web/parking-anatomy/benchmark.json`. It uses seeds 0–9, emits failures without replacing them with exact answers, and runs 150 workflows across five cases. Website builds consume this report; they do not execute the benchmark. The normal fixture export still refreshes the existing one-seed illustrative QAOA example.

| Case | Plan bits | Exact total flow | Exact mean flow |
|---|---:|---:|---:|
| Original two-car case | 8 | 90 min | 45 min |
| B deadline 30 | 6 | 90 min | 45 min |
| B arrival 30 | 6 | 90 min | 45 min |
| Three 25 kW cars, 12.5 kWh each | 12 | 120 min | 40 min |
| Two 50 kW modules, one 30-minute slot | 8 | 60 min | 30 min |

## Baselines and budgets

- Unchanged QAOA: two layers, 80 evaluations per restart, two restarts, 2,048 final shots per seed. Local ideal Aer statevector training and final sampling only.
- Native SciPy/HiGHS MILP: one assignment per car, gun occupancy and module power as explicit linear constraints. No QUBO penalties. Zero MIP relative gap; ten repeated solves, each including preparation and validation.
- Structured random: 2,048 draws per seed, each independently selecting one complete plan per car, then checking physical feasibility.
- Uniform unrestricted bitstrings: exact analytical feasibility reference only. It is not a fourth measured optimizer.

All methods receive identical input scenarios and generated plan fingerprints. The existing exact enumeration verifies MILP optima. An independent validator recomputes energy, power, occupancy and arrival/deadline rules directly from profiles. Review additionally compared native constraints and validation over all 4,736 bitstrings across the five cases without disagreements.

## Metrics and provenance

Each run records returned quality, relative gap, optimum hit, status, source fingerprint, timings and (for samplers) all observed bitstrings, feasible and optimal sample fractions. Qiskit count strings display the highest qubit first; returned bit vectors use x0 upward. Answers must actually occur in the histogram and have the best observed valid objective. There is no reference fallback when sampling fails.

Quality medians are conditional on valid answers; valid-answer, optimum-hit and error counts remain visible. Sampler metrics are N/A for MILP. Missing results are never converted to zero quality. Runtime medians include all runs, including errors. Failures keep their diagnostic messages.

Timing records candidate generation/formulation, training/solving/sampling, independent validation, and their total. `perf_counter` measures elapsed wall time; `process_time` measures process CPU time, summing threads. Interpreter/import startup and exact-reference computation are excluded. Aer time is simulation runtime, never QPU runtime. Methods rotate order between seeds. Aer uses one thread; HiGHS retains defaults. No affinity, resource isolation, hardware jobs or external services are used. Timing comparisons are machine-specific; equal final sample budgets do not represent equal computational work.

The versioned JSON contains case inputs, generated plans, complete configurations, seeds, environment/library versions, raw counts, per-run records, aggregates, analytical references and source hashes. `validate_report` rejects stale sources, mismatched inputs, incomplete protocol data, unsupported sampled answers and inconsistent metrics. Strict Python fixture export is the release gate. The frontend independently recomputes aggregates from raw runs and compares them with the report.

## Recorded outcome and limits

QAOA found the exact optimum in 49/50 runs. Its three-car seed 0 returned a valid suboptimal schedule (see raw records for the authoritative seed and result). MILP and structured random each found the optimum in all 50. MILP had lower median elapsed runtime in every case. Structured random also had higher median feasible-sample fractions in every case. These results demonstrate no quantum advantage.

The 60→45 minute illustration comes from allocation and scheduling on the same 50 kW module. It does not measure quantum speedup or improvement over an industry control system. Small 6–12 qubit instances do not establish scaling, practical utility or hardware performance. Stronger tuned classical methods, larger/harder families, matched tuning effort, noise and QPU execution remain untested.

The protocol draws on [Bucher et al., Towards Robust Benchmarking of Quantum Optimization Algorithms](https://arxiv.org/abs/2405.07624): use appropriate mathematical formulations, report full workflow costs and assess classical alternatives. This small demonstration is not an exhaustive fair-performance study. The hybrid mapping and cost/mixer workflow follow [standard QAOA](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm).
