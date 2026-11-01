# Shared-power EV station: QUBO formulation

The repository already contains a booking QUBO and a QAOA implementation in
`src/quantum_scheduler.py`. That original model reserves a single-port station
for an hour and minimizes electricity cost plus weighted waiting. It does not
model two guns drawing from one shared module.

The new model in `src/shared_power_scheduler.py` handles multiple independent
modules, each with two guns and a shared power limit. It minimizes total time
from arrival until the requested energy has been delivered. Both formulations
can use the existing Ising mapping, cost circuit, training loop, and sampler.

## Physical model and discretization

Inputs for car i are arrival a_i, deadline d_i, required energy E_i in kWh, and
maximum charging power V_i in kW. Module m has total power P_m and two guns.
P_m is the module's combined output limit, not a separate allowance per gun.
The number of guns is an explicit modeling assumption, not a claim about all
chargers in India.

Split a finite planning horizon into slots of length delta minutes, and choose
a power step s kW. Allowed powers are 0, s, 2s, ... up to both the car and module
limits. One energy unit is s * delta / 60 kWh. Each requested energy must be an
integer number of these units; the code rejects mismatches rather than rounding
them or silently overcharging a car. Arrivals and deadlines need not align with
the grid, but charging only occupies complete slots inside their time windows.

A candidate plan r contains:

- One car, one module, and one fixed gun.
- A power profile p_r(t) for every slot; its power can change between slots.
- A start at its first positive-power slot and completion C_r at the end of
  its last positive-power slot.

Classical preprocessing generates all individually feasible plans on this grid:

\[
0 \le p_r(t) \le \min(V_i, P_m),\qquad
\frac{\delta}{60}\sum_t p_r(t)=E_i.
\]

The plan cannot start before arrival or finish after the deadline. A car keeps
its gun during any zero-power pauses between starting and finishing, and leaves
when finished. It never switches module or gun during a session. Generating an
individual plan does not choose a multi-car schedule.

## Binary decisions and conflicts

Let R_i be the candidate plans for car i. Introduce one bit per plan:

\[
x_r = 1 \text{ if plan }r\text{ is selected; otherwise }0.
\]

Let K contain unordered pairs of plans for different cars that cannot both be
selected. Two plans conflict when they:

1. Occupy the same module's same gun during overlapping slots; or
2. Use the same module and their combined power exceeds P_m in any slot.

Plans on different modules do not conflict. Pairwise constraints suffice here
because each module has exactly two guns: any three overlapping sessions must
already have a same-gun conflict. Once gun conflicts are excluded, each module
has at most two simultaneous cars, so its aggregate power constraint is also
pairwise. A module with three or more guns would require a different capacity
encoding; this implementation rejects it.

## Objective and QUBO

Define the nonnegative plan cost c_r = C_r - a_i, in minutes. Minimize:

\[
F(x)=\sum_r c_r x_r
+\lambda\sum_i\left(\sum_{r\in R_i}x_r-1\right)^2
+\lambda\sum_{(r,s)\in K}x_rx_s.
\]

The three terms are total arrival-to-completion time, exactly-one-plan penalties,
and physical-conflict penalties. Every car must be served. For a fixed number
of cars, minimizing total time also minimizes average time. Pauses during a
session count toward this objective, even though `waiting_minutes` reports only
the wait before charging first starts. This objective differs from minimizing
the last car's completion time or maximizing instantaneous utilization.

Since x_r squared equals x_r, the coefficients returned by the builder are:

\[
\text{constant}=\lambda N,\qquad L_r=c_r-\lambda,
\]

\[
Q_{rs}=\begin{cases}
2\lambda & r,s\text{ are different options for the same car},\\
\lambda & (r,s)\in K,\\
0 & \text{otherwise}.
\end{cases}
\]

`quadratic[(r, s)]` stores each unordered pair once, with r < s. These are
polynomial coefficients; do not double them as if they were entries in both
halves of a symmetric matrix.

The builder uses the safe bound:

\[
B=\sum_i\max_{r\in R_i}c_r,\qquad\lambda=B+1.
\]

Any valid schedule costs at most B. Any invalid bitstring has a nonnegative
operating cost and at least one unit of penalty, so costs at least lambda > B.
Consequently, if a feasible schedule exists, a global QUBO minimum is feasible
and optimal on the generated grid. Custom penalties must also exceed B. This
does not guarantee that an approximate quantum solver finds that minimum.

## Worked eight-bit instance

Use a 50 kW dual-gun module, two 30-minute slots, and 25 kW power increments.
Car A accepts up to 50 kW and needs 37.5 kWh; car B accepts up to 25 kW and needs
12.5 kWh. Both arrive at minute 0 and must finish by minute 60.

| Bits | Car | Gun | Power in slots 1, 2 (kW) | Completion / cost (min) |
| --- | --- | --- | --- | ---: |
| x0, x1 | A | 0, 1 respectively | 25, 50 | 60 |
| x2, x3 | A | 0, 1 respectively | 50, 25 | 60 |
| x4, x5 | B | 0, 1 respectively | 0, 25 | 60 |
| x6, x7 | B | 0, 1 respectively | 25, 0 | 30 |

There are four options per car, B = 120, lambda = 121, constant = 242, and
L = [-61, -61, -61, -61, -61, -61, -91, -91]. Every same-car pair has coefficient
242; every cross-car conflict has coefficient 121. Run the demo to inspect all
pair coefficients.

The classical reference optimum is x0 = x7 = 1, or the equivalent gun-swapped
solution x1 = x6 = 1:

| Interval | A | B | Module total |
| --- | ---: | ---: | ---: |
| 0–30 minutes | 25 kW | 25 kW | 50 kW |
| 30–60 minutes | 50 kW | 0 kW | 50 kW |

A receives 12.5 + 25 = 37.5 kWh and finishes after 60 minutes. B receives
12.5 kWh and finishes after 30 minutes. Total flow time is 90 minutes; average
is 45 minutes. The module's full 50 kWh of output over one hour is required,
so finishing everyone in less than an hour is physically impossible here.
The example verifies the encoding; it does not claim an improvement over an
existing charger's dynamic-sharing policy.

## Run and prepare the quantum model

```sh
# Build coefficients and run a separate exact classical reference.
.venv/bin/python shared_power_demo.py

# Also execute the existing QAOA circuit on local Aer.
.venv/bin/python shared_power_demo.py --qaoa

# Verify both the original and new models.
.venv/bin/python -m unittest discover -s tests -v
```

```python
from shared_power_demo import sample_shared_power_scenario
from src.shared_power_scheduler import build_shared_power_qubo
from src.quantum_scheduler import qubo_to_ising, build_qaoa_circuit, solve_qaoa

model = build_shared_power_qubo(sample_shared_power_scenario())
ising = qubo_to_ising(model)       # x_r = (1 - Z_r) / 2
circuit = build_qaoa_circuit(ising, layers=2)
result = solve_qaoa(model)         # Validates only schedules actually measured.
```

This direct encoding uses eight qubits for eight candidate-plan bits. The
sampler independently checks energy, vehicle limits, module power, gun occupancy,
and time windows. An invalid or absent feasible sample never triggers a
classical replacement. The exact reference is an explicitly separate check.

## Scope and scaling

This first formulation assumes known arrivals and energy demands, constant car
power ceilings, controllable grid-aligned power levels, 100% efficiency, and
immediate departure when finished. Confirm those control capabilities against
the intended hardware. Battery taper, temperature effects, switching delays,
minimum session power, and cars staying parked after completion are not modeled.

Modules have independent power budgets; the grid supply is assumed sufficient
to power all modules simultaneously. A binding station-wide power cap would
need an additional aggregate constraint, such as integer slack variables and
quadratic penalties; `site_power_kw` below the sum of module ratings is rejected.
Power cannot be transferred from one module to another in this formulation.

The QUBO is exact over the enumerated discrete plans, not over every possible
continuous charging policy. Finer grids may improve schedules, but generation
can grow exponentially, and one bit per complete plan can require many qubits.
The generator stops after 1,000 options per car by default. The local QAOA solver
also checks a configurable 20-qubit simulation limit before allocating a
statevector. This is a small-instance quantum formulation, not a claim of
station-scale deployment or quantum advantage. A larger implementation should
consider time-indexed power variables, decomposition, or restricted plan sets
and measure the resulting trade-offs.
