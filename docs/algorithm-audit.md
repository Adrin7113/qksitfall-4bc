# Algorithm audit — 1 November 2026

Scope: the original station/hour-slot booking optimizer, the dual-gun
shared-power optimizer, their QUBO/Ising/QAOA paths, and the website's
representation of both. This is a correctness and modeling audit, not a
performance or quantum-advantage benchmark.

## Findings and fixes

| Finding | Impact | Resolution |
| --- | --- | --- |
| Original bookings used station power even when a vehicle ceiling was supplied | Charging duration and slot feasibility could be optimistic | Validate optional `max_power_kw`; use the minimum of station and vehicle power for duration and energy capacity |
| Shared-model energy alignment checked tolerance in unit counts while decoding checked kWh | `required_energy_kwh=37.5000001` passed generation but every generated plan failed physical validation | Compare grid alignment in kWh, using the same absolute tolerance as decoding |
| Power discretization added tolerance after dividing by the power step | A 24.9999999 kW ceiling could generate a 25 kW profile that decoding rejected | Apply the tolerance to the physical kW ceiling before division |
| Profile generation recursed once per slot | A valid 1,440-slot horizon could raise `RecursionError` before the candidate budget applied | Replace recursion with iterative depth-first search, preserving completeness and ordering |

The vehicle power ceiling is optional for backwards compatibility. When it is
absent, the original model assumes the vehicle accepts the station-rated power.
Its existing sample is unchanged.

## Architecture finding: integration is still planned

The original `generate_options` / `solve_exact` pipeline jointly chooses a
station and a full hourly booking. Its objective is electricity bill plus
weighted pre-charge waiting, measured in preference points. Each station has
one port. Travel consumption, arrival reserve, charging energy, completion
deadline and slot capacity are checked before optimization.

The new `build_shared_power_qubo` pipeline handles modules and guns within a
station. It chooses one complete, possibly time-varying power plan per vehicle.
Its objective is total arrival-to-completion time in minutes, equivalent to
average time when all vehicles must be served.

These are separate implemented examples, not an integrated station recommender.
The old model does not request completion/price offers from the new model.
Their scores use different units and cannot be compared directly. A future
interface should pass arrival time, arrival energy, requested energy and
vehicle capability into the local scheduler, then return feasibility, expected
completion and price to station selection. Binding reservations and unexpected
arrivals would also need explicit handling.

## Mathematics checked

- Each shared-power option meets its energy requirement, vehicle power ceiling,
  arrival window and deadline on the declared grid.
- Exactly-one-plan penalties and pairwise conflict penalties agree with an
  independent physical checker, including gun occupancy during charging pauses.
- Pair conflicts are sufficient because there are exactly two guns per module;
  budgets for different modules are independent.
- The automatic penalty exceeds every valid schedule's objective bound.
- Original and new QUBO energies match their Ising energies and bit ordering.
- QAOA's cost/mixer gates match independent phase and tensor-product mixer
  calculations, including the exact operations exported to the browser.
- Quantum results are selected only from valid strings actually sampled.
  The exact solver is a separate reference, never a silent fallback.

## Reproducible validation

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/audit_algorithms.py
node web/parking-anatomy/build.mjs
node web/parking-anatomy/build.mjs --light
node web/parking-anatomy/check.mjs
node web/parking-anatomy/check-shared.mjs
node web/parking-anatomy/motion-check.mjs
.venv/bin/python web/parking-anatomy/audit_circuit.py
```

Results:

- 55 Python tests pass, including regressions for the fixes above.
- Deterministic stress audit: 75 small scenarios, 90,336 binary assignments,
  100 profile-completeness checks and six boundary regressions pass. Five
  generated cases above the 14-bit exhaustive limit are explicitly skipped.
- Browser-model checks: 3,232 original Python/browser/QUBO/Ising comparisons,
  all 256 new shared-power states, and all four new presets pass.
- All 101 original circuit layouts retain gate ordering and stage boundaries;
  the new circuit has eight qubits, two layers, and 48 RZZ operations.
- Independent statevector checks: 303 original and three shared-power cases
  pass; maximum amplitude errors are below 1.3e-15 and 4.6e-16 respectively.
- Existing parking geometry, 64 pose transitions and 120 interrupted-motion
  cases pass.
- Browser checks cover sharing, delayed charging, overload, gun conflicts,
  individual bit selection, saved Aer answer, existing preference controls,
  circuit inspection, dark/light themes and responsive layout.

The website uses Python-exported data and actual circuit operations. Browser
interaction evaluates those data classically. Its displayed Aer result is a
saved local execution, not a live browser circuit run.

## Remaining limitations

Both reference solvers are exhaustive educational baselines; neither is a
strong classical benchmark for a quantum-advantage claim. The shared-power
candidate-plan representation can grow exponentially, and its direct circuit
uses one qubit per candidate plan. Candidate and simulator limits are explicit.

The shared model assumes known arrivals, constant vehicle power ceilings,
controllable grid-aligned power, 100% efficiency, fixed module/gun during a
session, retained occupancy during pauses, and immediate departure when done.
It has no battery taper or prediction uncertainty. A binding station-wide
power cap is explicitly rejected; no power transfers between module budgets.

No quantum advantage or improvement over a real charger's existing dynamic
sharing policy has been demonstrated. Those require matched, realistic
benchmarks and hardware control verification.

## Current model validity and scaling

The consolidated notebook now includes booking and final-charge fairness. The [model-validity and scaling review](model-validity-and-scaling-review.md) distinguishes exact mathematical/circuit checks from performance and physical validation, derives assignment/aggregate classical baselines, and documents hypothetical resource accounting without a quantum-savings claim. The older completion-time benchmark remains a separate model.
