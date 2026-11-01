# Model validity and scaling review

Reviewed 2026-11-01. Scope: the Charging Slot Scheduler and final-charge fairness models in the consolidated notebook. The older shared-power/completion-time model is a separate objective and benchmark. All circuit execution remains local classical simulation; no QPU or physical charger is used.

## Conclusion

Both models are mathematically valid under their declared assumptions, and their simulated circuits implement coherent QAOA cost/mixer evolution. They are representative **simplified optimization problems**, not validated operational charger controllers. Neither experiment establishes computational hardness, quantum advantage, a scalable quantum implementation, or a numerical resource saving at fleet scale.

The important classical comparisons are stronger than exhaustive bitstring search: booking is minimum-cost assignment; the current two-car fairness model has an exact O(T) aggregate-energy solver. The fairness rank table already solves its bounded instance during classical preprocessing, before QAOA runs.

## What has actually been checked?

| Layer | Evidence | What it does not establish |
|---|---|---|
| Booking mathematics | 101 waiting weights ×32 states: physical validity, direct penalties, QUBO and Ising agree exactly | All conceivable scheduling variants or negative-price penalty safety |
| Fairness mathematics | 100 scenarios ×4,096 states: feasibility, complete objective ordering, ties and exact reference agree | All possible real inputs or larger fleets |
| Circuit implementation | Four scenarios ×three angle settings; included JavaScript/NumPy/Qiskit probabilities agree within numerical tolerance | A formal unitary-equivalence proof for every angle/input |
| Sampling | Fresh Qiskit samples are decoded; invalid outcomes remain visible; exact answers stay separate | Guaranteed optimal sampling, escape from local minima, or improved end-to-end runtime |
| Noise plumbing | Optional 256-shot Aer/FakeManilaV2 booking test | Current QPU performance, fairness-noise performance, or fault-tolerant resources |
| Physical system | Constant-power mock scenarios only | Measured charging curves, losses, thermal limits, uncertain arrivals, communications or real station control |

The notebook saves the exact package versions, inputs, parameters, counts and checks. `notebooks/test_classical_and_scaling.py` separately tests assignment against 101 notebook weights and 60 randomized graphs, a shared bottleneck, fairness against 100 encoded scenarios, aggregate feasibility for horizons 1–6 and all two-car capability pairs, plus projection/shot arithmetic. These are finite tests backed by the model-specific derivations below, not a universal empirical validation claim.

## Charging Slot Scheduler: model and quantum mapping

One binary variable selects each individually feasible vehicle/station/hour appointment. A booking occupies the full nonoverlapping hour at one single-port station. Physical preprocessing checks travel consumption, reserve, arrival, energy capacity and actual completion deadline.

The score is electricity bill plus weighted waiting, in **preference points**, rather than a second monetary bill. Exactly-one-per-car squares and same-resource conflicts penalize invalid combinations. For nonnegative scores, let B be the sum of each car's maximum option cost and P=B+1. Any feasible schedule costs at most B. Every invalid binary assignment has at least one integer violation and costs at least P. When a feasible assignment exists, no invalid state can minimize this cost. Negative rewards, a user-selected smaller penalty or infeasible option sets need separate treatment.

Substitution x=(I−Z)/2 gives the Ising operator. RZ and RZZ cost rotations use the factor of two required by their definitions; RX(2β) is the X mixer. Omitting the identity offset changes only global phase. Qiskit count strings are parsed as binary integers with qubit0 as the least-significant bit. This follows [IBM's QAOA mapping](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm) and [bit-order conventions](https://quantum.cloud.ibm.com/docs/en/guides/bit-ordering).

**Classical baseline.** Cars form one side of a bipartite graph and station/hour resources the other. Eligible appointments are edges with additive scores. A minimum-cost matching covering every car is exactly this optimization problem. The implementation uses [SciPy's rectangular assignment solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html), explicitly rejecting incomplete/infeasible assignments. A sparse [minimum-cost-flow formulation](https://developers.google.com/optimization/flow/assignment_min_cost_flow) is another appropriate baseline. More options alone do not turn this family into arbitrary hard scheduling.

Default optimum: A takes North09:00–10:00, B takes North08:00–09:00; bill₹28.80, waiting70 minutes, score46.30. Increasing the waiting preference to1 changes the optimum and score. Objective value and bill must remain distinct.

## Final-charge fairness: exact objective, limited quantum construction

Two cars remain in their stated dock-presence condition for four 15-minute intervals. The station cap is50 kW; discrete levels are0/25 kW, plus50 kW for a capable car. Reject absent-car charging, unsupported power and battery overfill. Maximize the lower **final** percentage among present cars, then total delivered energy. Price is reported separately. This is not equal added energy, requested-energy satisfaction, or full lexicographic fairness across every car in an arbitrary fleet.

The twelve-bit encoding uses three bits per interval for six joint power choices and two invalid codes. For a fixed input, rank achievable minimum final percentages from0 to m−1. A feasible state with rank r and delivered6.25-kWh block count u has E=9(m−1−r)+8−u. Invalid cost is9m. A one-rank improvement dominates every possible energy tie-break, and every invalid state is strictly worse than every valid one. Exact rational comparisons avoid headroom/tie drift.

This is a valid **diagonal Hamiltonian, not a quadratic QUBO**. Its phase is unitary, but `DiagonalGate` is not a free native hardware primitive. The implementation enumerates every state and records the winners before training. It therefore studies quantum sampling over an already classically solved cost landscape. Rank compression preserves the optimum/order but changes gaps, normalization and potentially QAOA performance. The original [QAOA paper](https://arxiv.org/abs/1411.4028) provides no universal finite-depth guarantee for this application; COBYLA and restarts do not guarantee escape from local minima.

**Exact O(T) classical baseline.** A 25-kW quarter-hour supplies6.25 kWh. Let mᵢ be the per-slot ceiling in25-kW units and Uᵢ=min(Tmᵢ, floor(Cᵢ(100−sᵢ)/625)); absent cars have Uᵢ=0. Feasible totals satisfy 0≤uᵢ≤Uᵢ and u₁+u₂≤2T. These conditions are sufficient here: place a slow car's units in distinct slots, then fill residual capacity for a fast car; two slow cars can overlap without exceeding50 kW.

For each u₁, set u₂=min(U₂,2T−u₁). Increasing u₂ cannot reduce the primary objective and improves its energy tie-break. Thus only U₁+1≤2T+1 objective evaluations are needed, followed by O(T) schedule reconstruction. This counts rational arithmetic operations; bit precision and output size still matter. The default has30 feasible totals but only **four** boundary objective evaluations, yielding76.875% minimum and50 kWh. With B limited to25 kW, four evaluations yield61.25% and43.75 kWh. These are model outcomes, not monetary or quantum resource savings.

More fixed-present cars can be represented by integral car-to-slot flow; max-min thresholds impose lower delivered-energy requirements, followed by a maximum-flow energy tie-break. Known arrival windows remove edges rather than automatically proving hardness. Different nonlinear, nonpreemptive, routing or coupled-grid models need new derivations and appropriate exact/heuristic classical baselines. Do not transfer a general NP-hardness claim to these special cases.

## Why “the quantum run found the optimum” is insufficient

The default fairness encoding has ten optimal states out of 4,096. For 2,048 independent uniform bitstring samples, the chance of at least one optimum is

`1 − (1 − 10/4096)^2048 ≈ 99.33%`.

This is an analytical reference, not a timed optimizer experiment. The trained distribution changes the per-shot probabilities, but matching the optimum in four examples does not demonstrate better time-to-solution than assignment/totals/structured sampling. A feasible sample is not an optimality certificate. The earlier saved completion-time benchmark also found no quantum advantage; its timings belong to that different model and must not be reused as a fairness benchmark.

## Hypothetical larger systems: counts we can responsibly calculate

The notebook computes these formulas without allocating large arrays. They are **representation/accounting scenarios**, not supported fleet inputs or future hardware forecasts.

For booking, one bit per eligible option gives q=M≤N×S×T. For100 cars,10 stations and24 hourly slots, the loose upper bound is24,000 option bits; eligibility filtering can reduce it. This does not predict a machine requirement or establish classical intractability.

For a hypothetical fairness station with N fixed-present cars/docks, F fast-capable cars, the same50 kW budget and T quarter-hour intervals, there are K=1+N+F+C(N,2) station-feasible choices per interval before headroom checks. A per-slot binary code uses q=Tceil(log₂K). This extension is not implemented; additional cars do not add charging capacity. A longer-horizon rank cost would need a weight 2T+1, not the current fixed9.

| Hypothetical all-fast cars | Quarter-hour intervals | Logical decision wires | Full complex128 statevector payload | One float64 cost table |
|---:|---:|---:|---:|---:|
|2|4|12|64 KiB|32 KiB|
|2|24 (six hours)|72|64 ZiB|32 ZiB|
|100|4|52|64 PiB|32 PiB|
|1,000|96 (one day)|1,824|2^1828 bytes|2^1827 bytes|

Payload formulas are16×2^q and8×2^q bytes; [Aer documents the statevector storage](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html). Python objects, buffers, probabilities and circuits add overhead. These are not lower bounds for every simulation method, the memory of the best classical scheduling solver, or physical-QPU memory. “52 qubits saves64 PiB of classical scheduling RAM” would be an invalid inference.

Generic diagonal synthesis can require exponentially many elementary gates; see [Bullock–Markov](https://arxiv.org/abs/quant-ph/0303039). That generic result is not an exact bound for every specially structured fairness cost, nor does it apply to every sparse booking QUBO. A compact arithmetic cost circuit would need to be designed and validated separately.

For independent fixed-circuit shots with known optimum probability p, S=ceil(log(1−c)/log(1−p)) gives probability c of at least one optimum. At95%, assumed p=0.001 needs 2,995 shots, p=10⁻⁶ needs 2,995,731 shots, and p=10⁻⁹ needs 2,995,732,273 shots. These are sensitivity calculations, **not an assumed p(N) scaling law**. They omit finite-shot training, calibration and noise and do not certify observed optimality.

Logical decision wires are not physical error-corrected qubits. No physical/logical multiplier, wall-clock quantum runtime, energy saving or money saving is justified without an architecture, compiled algorithm, error model and target failure probability.

## What a useful scaling benchmark would require

1. Preserve the same objective, feasible set and output obligations at every size; separate booking, fairness and completion-time experiments.
2. Compare against assignment, aggregate allocation or flow where their assumptions hold, and suitably tuned MILP/CP-SAT/heuristics for genuinely broader variants.
3. Count parsing, physical candidate generation, cost-table/oracle compilation, optimization evaluations/restarts, training shots, final shots, validation and reconstruction. Include target-specific routing, error suppression/correction and reset/readout for hardware. Report queue latency separately.
4. Report time and resources to equal solution quality and success confidence, across seeds and sizes. Separate cold setup from warm solve time and solver work from independent validation overhead.
5. Validate physical assumptions with measured charger/vehicle data before claiming better station operation. Extra energy from better scheduling is not automatically lower computational cost; neither creates extra station power.

Current conclusion: computational savings at very large scale are **unknown and not demonstrated**. This is missing algorithmic and physical evidence, not merely missing access to a bigger QPU.

## Website placement and model identity

After each circuit diagram, show a small “Validity & scale” disclosure linked to this review and the executed notebook. Suggested copy:

> Exact classical checks validate these small models and their simulated circuits. Both current problems also have efficient classical solutions; no quantum speedup or resource saving is demonstrated. The fairness cost table is compiled exhaustively before simulation. Explore the notebook for assumptions and hypothetical scaling counts.

The website's integer-tick fairness cost and the notebook's rank cost preserve the same objective but have different gaps, code ordering and distributions. Validate each implementation against its own Qiskit circuit; do not reuse angles, bitstrings or shot probabilities across them without conversion. The disclosure should follow the visual explanation rather than interrupt it or imply that qubit count predicts practical savings.
