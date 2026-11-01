# EV charging optimization: circuits, simulations and validation

Two educational models connect charging decisions to quantum circuits:

| Model | What it optimizes | Implementation |
|---|---|---|
| **Charging Slot Scheduler** | Electricity bill plus weighted waiting; one compatible station/hour booking per car | Five-qubit QUBO/Ising and QAOA |
| **Fair charging** | Lower final battery percentage first, then total energy for two docked cars | Twelve-qubit diagonal-cost QAOA; not a quadratic QUBO |
| Shared-power extension | Arrival-to-completion time with module/gun/power constraints | Separate Python example and saved benchmark |

All quantum execution here is **local classical simulation**. No real QPU, API key or charger controller is used. The models and circuit mappings have passed finite mathematical and numerical checks. Neither quantum advantage nor fleet-scale computational savings has been demonstrated. Both main models have strong exact classical baselines.

Start with the [executed, self-contained Jupyter notebook](notebooks/ev-scheduling-validation.ipynb), the [model-validity and scaling review](docs/model-validity-and-scaling-review.md), or the [interactive tech demo](https://qksitfall-parking-anatomy.glitchyie.chatgpt.site/). The website presents slot scheduling first, then fair charging as a deeper example. Browser simulation and Python/Qiskit execution are labelled separately; the website's tick-cost fairness encoding differs from the notebook's rank-cost encoding.

## Reproduce the notebook

The notebook includes its complete sources, derivations, exact audits, circuit simulation, sampling, classical comparisons and hypothetical resource calculations. Its independent environment uses Python3.13 and does not change the main application's Python requirement.

```sh
uv sync --project notebooks --locked --python 3.13.5
uv run --project notebooks python notebooks/execute.py
uv run --project notebooks python notebooks/test_classical_and_scaling.py
```

Open the notebook in a Jupyter client using `notebooks/.venv`, or upload it to an online Python notebook host and follow its setup cell. The runner saves executed outputs and [reproducible result JSON](notebooks/ev-scheduling-validation-results.json). Node.js is needed for the optional included browser-engine parity test. See [notebook setup](notebooks/README.md) for details. IBM's retired cloud simulators are not used.

## Evidence and limits

- **Mathematical checks:** 3,232 booking state/weight comparisons;409,600 fairness state/scenario comparisons, including feasibility, ordered objectives, ties and edge cases.
- **Circuit checks:** four scenarios at three angle settings; Qiskit and the included browser engine agree to numerical precision. Optional FakeManilaV2/Aer noise is a local snapshot test.
- **Classical comparison:** booking is minimum-cost assignment; the present fairness model has an exact O(T) totals solver. Its default optimum takes four aggregate objective evaluations. Exhaustive bitstring search is a correctness oracle, not the sole performance baseline.
- **Scaling:** the notebook calculates explicitly hypothetical logical-wire counts, statevector/table payloads and shot sensitivity. Those are not predicted resource savings or physical-qubit estimates. The fairness table is compiled by exhaustive enumeration before training.
- **Physical scope:** mock vehicle inputs, discrete power blocks, constant power/ideal efficiency and fixed presence. No measured operational benefit, charging-curve validation or hardware advantage is claimed.

Finding an optimum sample is not a guarantee of optimal sampling or a proof of speedup. Invalid/no-valid samples remain visible; exact answers are separate comparisons. Read the [review](docs/model-validity-and-scaling-review.md) for the proofs, sources, resource formulas and requirements for a fair larger-system benchmark.

## Repository map

```text
notebooks/                   # consolidated notebook, outputs, exact baselines, resource formulas
src/                         # original booking and shared-power Python implementations
main.py                      # booking QAOA command-line example
shared_power_demo.py         # separate completion-time sharing example
docs/                        # derivations, audits, review and benchmark protocol
web/parking-anatomy/          # retained standalone explainer and exported fixtures
quantum-ev-learning-guide/    # LaTeX lessons and glossary
tests/                       # original Python tests
output/                      # retained figures, PDF and historical artifacts
```

## Original Python examples

Use the main project's environment and Python version declared in `pyproject.toml`:

```sh
uv sync
uv run python main.py
uv run python main.py --layers 1 --show-circuit
uv run python shared_power_demo.py --qaoa
uv run python -m unittest discover -s tests -v
```

The detailed [booking-to-QAOA walkthrough](docs/booking-qaoa-walkthrough.md) retains the equations, five booking choices, gate factors, optimizer controls and bit-order explanation. The [shared-power formulation](docs/shared-power-qubo.md) concerns completion time, not final-charge fairness. The [algorithm audit](docs/algorithm-audit.md) documents earlier correctness fixes.

The [saved shared-power benchmark](docs/quantum-benchmark.md) compared QAOA with native MILP and structured random sampling over five small cases. It demonstrated no quantum advantage; its timings must not be presented as a fairness benchmark or large-scale projection.

For lessons see the [LaTeX source](quantum-ev-learning-guide/main.tex) and [compiled PDF](output/pdf/quantum-ev-learning-guide.pdf). Build the retained standalone explainer with `node web/parking-anatomy/build.mjs`; its README describes cached exports and preview behavior. It is distinct from the current hosted tech-demo release.
