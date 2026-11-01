# EV scheduling simulation notebook

Open [ev-scheduling-validation.ipynb](ev-scheduling-validation.ipynb) and choose **Restart Kernel → Run All**. The notebook contains the complete model sources, mathematical derivations, audits, Qiskit circuit construction, seeded optimizer, sampler, optional JavaScript parity check and a local fake-device noise test. It uses mock data and never submits a real quantum job or controls a charger.

## Run from this repository

This directory has an isolated Python 3.13 validation environment. It does not change the main project's Python requirement or dependencies.

```sh
uv sync --project notebooks --locked --python 3.13.5
uv run --project notebooks python notebooks/execute.py
```

The runner executes every notebook cell with this environment's kernel and saves the notebook outputs plus [ev-scheduling-validation-results.json](ev-scheduling-validation-results.json). It creates and cleans temporary support sources; no external repository files are needed by the notebook. Node.js is needed only for the optional browser-engine parity check; an absent Node runtime is reported as skipped.

For interactive use, open the notebook in an existing Jupyter client and select the Python interpreter in `notebooks/.venv`. On an online Python host such as Colab, upload this one notebook; its dependency cell uses `uv pip` to install the tested package versions if needed. If uv is absent, install it following the linked official instructions first. No notebook has been uploaded to another account on the user's behalf.

## Models

- **Booking:** five qubits, fixed two-station mock scenario, bill plus weighted waiting, one booking per car and no shared-port conflict. The penalty proof depends on nonnegative costs. The waiting preference is editable through the documented Python input.
- **Fairness:** twelve qubits, two cars, four 15-minute intervals, 50 kW station cap, vehicle capabilities/presence/headroom, maximize lower final battery percentage then total kWh. An exact rank-based diagonal Hamiltonian preserves the ordered objective. It is **not a quadratic QUBO**; constructing its table already enumerates the finite state space.

The earlier eight-qubit completion-time sharing model is a distinct objective and is not substituted for fairness. Existing application scripts and website behavior are unchanged.

## Recorded validation

- All 14 code cells executed with zero errors.
- Booking: 3,232 exact physical/direct-penalty/QUBO/Ising comparisons across 101 waiting weights.
- Fairness: 409,600 state/scenario checks across 100 scenarios, including complete objective ordering and an independent classical reference.
- Four experiments at three angle settings each: Qiskit circuits and the included JavaScript statevector engine agree within about 3.01e-16 probability error in the recorded run.
- All four recorded ideal-simulation runs sampled an optimum. Invalid samples still occurred; neither feasibility nor optimality is guaranteed by shallow QAOA.
- Optional 256-shot FakeManilaV2/Aer booking simulation completed locally with approximate stored-snapshot noise. It is not a current device measurement or a fairness-noise benchmark.

Saved counts are evidence of one run, not prescribed answers. Optimizer results may vary with numerical libraries/platforms. The notebook never silently replaces failed samples with exact winners and makes no quantum advantage claim.

## Why a notebook instead of an IBM cloud project?

IBM [retired its cloud simulators](https://quantum.cloud.ibm.com/docs/en/guides/local-simulators) and documents Aer/fake backends as [local testing](https://quantum.cloud.ibm.com/docs/en/guides/local-testing-mode). Composer provides circuit visualizations and QASM files; a currently supported hosted, shareable Python mock-project service was not verified. The notebook can be shared through the repository or uploaded to another Jupyter host. See [IBM's QAOA workflow](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm) and the [Colab sharing/runtime explanation](https://research.google.com/colaboratory/faq.html).
