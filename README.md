# Quantum EV charging with Qiskit QAOA

The [algorithm audit](docs/algorithm-audit.md) records correctness fixes,
reproducible stress checks, and the still-planned interface between station
selection and the local shared-power scheduler.

For the **two-gun shared-power module problem**, see the
[QUBO formulation and worked example](docs/shared-power-qubo.md). It supports
multiple modules, vehicle power limits, changing power allocations, and an
arrival-to-completion time objective. Run it separately from the original
booking example below:

```sh
.venv/bin/python shared_power_demo.py
.venv/bin/python shared_power_demo.py --qaoa
```

For the full learning document with typeset equations, worked derivations, a
glossary, and exercises with answers, open the
[LaTeX project](quantum-ev-learning-guide/main.tex) or the
[compiled PDF](output/pdf/quantum-ev-learning-guide.pdf).

The default program now builds and runs a quantum optimization circuit. It uses
Qiskit Aer locally: no API key or IBM hardware access is needed. Ordinary Python
still computes travel, energy requirements, and possible bookings; QAOA searches
for a compatible combination of those bookings.

```sh
.venv/bin/python main.py
.venv/bin/python main.py --layers 1 --show-circuit
.venv/bin/python -m unittest discover -s tests -v
```

Read `src/quantum_scheduler.py` in order. The functions mirror the six quantum
checkpoints printed by `main.py`. Change vehicle/station inputs in
`sample_scenario()` in `main.py`.

## 1. Encode bookings as qubits: build_qubo()

First, `generate_options()` handles driving consumption, arrival reserve,
charging power, and deadlines. It provides the following five possible bookings.
A value of 1 means selecting the booking; 0 means not selecting it.

| Qubit / variable | Booking | Electricity bill | Waiting | Booking score |
| --- | --- | ---: | ---: | ---: |
| q0 / x0 | A, North, 08:00 | Rs 20.80 | 5 min | 22.05 |
| q1 / x1 | A, North, 09:00 | Rs 10.40 | 65 min | 26.65 |
| q2 / x2 | A, South, 08:00 | Rs 33.00 | 0 min | 33.00 |
| q3 / x3 | A, South, 09:00 | Rs 22.00 | 60 min | 37.00 |
| q4 / x4 | B, North, 08:00 | Rs 18.40 | 5 min | 19.65 |

Booking score = electricity bill + 0.25 * waiting minutes. Five booking bits
use five qubits in this deliberately direct encoding. We retain B's single
booking as a qubit to keep the encoding easy to follow; fixing forced decisions
classically could reduce the circuit size in a later experiment.

## 2. Build the QUBO: build_qubo(), qubo_value()

The objective must encode costs AND invalid schedules:

```text
f(x) = 22.05*x0 + 26.65*x1 + 33*x2 + 37*x3 + 19.65*x4
     + P*(x0 + x1 + x2 + x3 - 1)^2
     + P*(x4 - 1)^2
     + P*x0*x4
```

The first penalty enforces exactly one booking for A. The second requires B's
booking. The last penalizes both cars using North in the early slot.

Expanding the squares uses the fact that x*x=x for binary variables. The result
contains only a constant, individual-bit coefficients, and pair coefficients.
Those are stored as `constant`, `linear`, and `quadratic` in the model.

The safe automatic penalty is `sum(max score for each car) + 1`. Here that is
37 + 19.65 + 1 = 57.65. Any valid schedule costs at most 56.65, while any invalid
assignment incurs at least one 57.65 penalty on top of nonnegative booking
costs. This bound is calculated without solving or enumerating schedules.

You can override it with `--penalty`, but a smaller value can make an invalid
assignment preferable. Larger penalties can also make training focus on
feasibility at the expense of distinguishing costs among feasible schedules.

## 3. Turn costs into quantum gates: qubo_to_ising(), build_qaoa_circuit()

A quantum cost operator uses Z rather than binary x. Z has eigenvalues +1 for
bit 0 and -1 for bit 1. Therefore the substitution is:

```text
x[i] = (1 - Z[i]) / 2

L*x[i]        -> L/2 - L*Z[i]/2
Q*x[i]*x[j]   -> Q/4 * (1 - Z[i] - Z[j] + Z[i]*Z[j])
```

`qubo_to_ising()` collects the resulting Z terms, ZZ terms, and constant offset
in a Qiskit `SparsePauliOp`. The tests check the energy of all 32 basis states
against the original QUBO to verify both the math and the qubit ordering.

The circuit is constructed explicitly, so you can inspect its operations:

```python
circuit.h(range(circuit.num_qubits))

# For each layer, using the derived coefficients:
circuit.rz(2 * gamma[layer] * z_coefficient / scale, qubit)
circuit.rzz(2 * gamma[layer] * zz_coefficient / scale, i, j)
circuit.rx(2 * beta[layer], qubit)
```

- H gates prepare the initial uniform superposition.
- RZ and RZZ gates form the cost layer, changing phases according to costs.
- RX gates form the mixer, allowing phase differences to change outcome
  probabilities. The cost layer alone does not change measurement probabilities
  when starting from uniform superposition.
- `gamma` controls cost evolution, and `beta` controls mixing. A depth of p
  layers gives 2p adjustable angles. H gates occur only at the start.

The factor of two appears because RZ(theta) implements exp(-i*theta*Z/2),
whereas the desired cost operation is exp(-i*gamma*coefficient*Z).

We divide the Hamiltonian coefficients by their largest absolute value to keep
angle scales manageable. Multiplying all costs by the same positive scale does
not change the minimizer. The constant offset only causes a global phase, so we
leave it out of the gates and restore it when reporting expected scores.

This follows the [QAOA workflow in IBM's documentation](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm).

## 4. Train the angles: solve_qaoa()

COBYLA, a classical numerical optimizer, changes the circuit angles. It does
not choose car bookings or run an exhaustive scheduling algorithm.

```text
Propose angles
    -> Execute the parameterized circuit through Aer Estimator
    -> Obtain the expected QUBO score
    -> Propose new angles and repeat
```

For learning, training uses **ideal, exact expectation values** from Aer's
statevector simulator (`precision=0`). There is no finite-shot noise during
training. `--shots` controls the final measured circuit only.

Expected score is the average over the circuit's outcome distribution, including
penalties on invalid outcomes. It is different from the score of the best
feasible sample. Training seeks a lower expectation; it need not improve on
every evaluation, and may get stuck at a poor solution.

Each restart begins from different seeded angles. The program retains the best
angles it actually evaluated across all restarts. `history`, `angles`, and
`parameter_order` are available in the returned result for further experiments.
For this circuit Qiskit's parameter order is beta[0..p-1], then gamma[0..p-1].

## 5. Measure the circuit: summarize_counts(), decode_bits()

After training, we bind the best angles, append measurements, and run:

```python
measured.measure_all()
counts = AerSimulator(method="statevector").run(
    measured, shots=shots, seed_simulator=seed
).result().get_counts()
```

A shot is one repetition of circuit preparation and measurement. The default
4,096 shots produce a histogram of five-bit outcomes.

**Bit order matters:** Qiskit prints the highest-index qubit first. The displayed
string `10010` means q4=1, q3=0, q2=0, q1=1, q0=0. In our booking list order,
that is `[0, 1, 0, 0, 1]`. `summarize_counts()` reverses the displayed string.

`decode_bits()` then independently checks exactly one booking per car and no
charger double bookings. The program reports the fraction of shots that are
valid. The most frequent measured string can be invalid; frequency alone is
not a reason to accept it as a schedule.

## 6. Read the best feasible sampled schedule

The program selects the lowest booking score **among valid strings actually
measured**. It never fills in an unmeasured answer with a classical solver.

With the default settings and seed, the local run produced:

```text
Selected bits, q0..q4: [0, 1, 0, 0, 1]
A -> North, reserve 09:00-10:00
B -> North, reserve 08:00-09:00
Electricity bill: Rs 28.80
Total waiting: 70 minutes
Sampled schedule score: 46.30
Valid final samples: 1921 / 4096 (46.9%)
```

This is a measured result, not a guarantee of finding the global optimum.
Results can change with seeds, tuning, or library versions. A run with no valid
samples returns `no_feasible_sample`; that does not prove infeasibility. When
preprocessing proves that a vehicle has no booking, the CLI reports that before
running a circuit. There is no silent classical fallback.

## Experiments to improve the quantum search

Change one setting at a time and record both valid-sample fraction and best
feasible score. Keep training expectation separate from sampled schedule score.

```sh
# Inspect the simplest circuit.
.venv/bin/python main.py --layers 1 --show-circuit

# Give a deeper circuit more optimization budget and random starts.
.venv/bin/python main.py --layers 3 --iterations 300 --restarts 5

# Change final measurement coverage; this does not retrain with noisy estimates.
.venv/bin/python main.py --shots 16384

# Test whether the result depends on a favorable initialization.
.venv/bin/python main.py --seed 21
```

| Setting | What it changes | Trade-off |
| --- | --- | --- |
| `--layers` | Number of cost/mixer pairs | More expressive, but more angles and gates |
| `--iterations` | Objective evaluation budget per restart | More training time; may converge sooner |
| `--restarts` | Independent angle initializations | More opportunities to escape poor local solutions |
| `--shots` | Final measurement repetitions | More sampling coverage; no change to learned angles |
| `--seed` | Initial angles and final sampling randomness | Reveals variability rather than proving improvement |
| `--penalty` | Cost of constraint violations | Balances feasibility emphasis against operating costs |

The next code-level experiments are different mixers, better initialization,
noise models, finite-precision expectation estimates, and larger scenarios.
Aer statevector simulation uses exponentially growing memory. This is a small
quantum-algorithm learning project, not evidence of quantum speedup or a hardware
run. IBM hardware execution requires a separate Runtime integration; this
command does not use your API key.

Physical assumptions remain simple: one port per station, nonoverlapping
one-hour slots, one session per car, full-slot reservation, constant consumption
and charging power, 100% charging efficiency, and direct travel as soon as the
vehicle is available. Electricity is billed for energy actually needed.

## Interactive parking and quantum explainer


The Anatomy illustration in `web/parking-anatomy/` shows this same charging
example as a miniature parking lot, with a reservation board, waiting preference
controls, and a five-bit booking inspector. Build its standalone page with:

```sh
node web/parking-anatomy/build.mjs
```

Open `web/parking-anatomy/dist/index.html` in a browser. The build exports the
sample bookings from the Python scheduler; a saved fixture supports rebuilding
without Python. See `web/parking-anatomy/README.md` for preview instructions and
`AGENT_BRIEF.md` in that folder for the implementation brief.

The page computes the 32 illustrative QUBO energies classically and explains the
QAOA workflow. The browser page itself does not run QAOA or access quantum
hardware; its exported baseline still comes from the classical reference solver.
Run the Python command above to execute the actual quantum circuit.


## Comparative quantum evidence

Run `.venv/bin/python scripts/benchmark_quantum.py` to regenerate five deterministic cases and 150 measured workflows independently of website builds. The saved report compares unchanged QAOA with native SciPy/HiGHS MILP and structured random sampling. Current optimum hits: QAOA 49/50, MILP 50/50, structured random 50/50; MILP has lower median elapsed time in every case. No quantum advantage is demonstrated. See [protocol and interpretation](docs/quantum-benchmark.md) for timing boundaries, source freshness and reproduction commands.
