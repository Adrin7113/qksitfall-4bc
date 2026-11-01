# EV Scheduling Lab

## Presenting the judges' demo

The main page follows four numbered chapters in DOM and navigation order:

1. **Station choice:** start the demo, show A's conflicting first choice,
   restore the compatible plan, and change the waiting preference.
2. **Power sharing:** show the valid starting plan, optimize from 60 to 45
   minutes average time, then inspect an overload or gun conflict. The module
   remains 50 kW and final completion remains 60 minutes in both valid plans.
3. **Quantum model:** switch between the five-qubit station model and the
   eight-qubit shared-power model. Equations and circuits expand on demand.
4. **Results:** compare the starting plan, exact reference and saved local Aer
   answer. State the prototype's scope and the next benchmark clearly.

Use **Reset demo** before presenting. It restores the original station inputs,
the shared-power starting plan, the first quantum tab and collapsed technical
details. The technical audit is in the appendix for questions. The station
feedback interface is planned; the two scenarios are independent examples.

The page now presents two separate models: the original station/hour booking
optimizer and the new two-gun shared-power scheduler. The architecture overview
explicitly marks their station-offer feedback interface as planned. The new
panel includes four power-sharing presets, an eight-bit inspector, its QUBO,
an actual eight-qubit circuit, a downloadable model/circuit, a saved local Aer
run, and the algorithm audit. Browser interactions remain classical.

`export_fixture.py` exports both models directly from the Python project.
When building from a standalone Site source checkout, set `PARKING_SOURCE_ROOT`
to the repository root and `PARKING_PYTHON` to its interpreter. Set
`PARKING_REQUIRE_PYTHON=1` to reject a stale cached fixture during development.
Run `node check-shared.mjs` for all 256 shared-power energies, physical checks,
presets, saved-sample checks and eight-qubit gate layout checks.

A static IBM Carbon inspired educational page with an Anatomy charging-lot figure and an actual Qiskit circuit viewer. Dark Gray100 is the default; the theme control also supports light mode. IBM Plex fonts are hosted locally with their SIL license in vendor/fonts; Anatomy retains its MIT license.

From the repository root:

```sh
node web/parking-anatomy/build.mjs
node web/parking-anatomy/build.mjs --light
node web/parking-anatomy/check.mjs
node web/parking-anatomy/motion-check.mjs
python3 -m http.server 8765 --directory web/parking-anatomy/dist
```

Open http://127.0.0.1:8765/. The build uses the existing .venv Python to export the actual booking model and Qiskit circuit for all 101 waiting weights. Set PARKING_PYTHON to select another interpreter. A cached complete fixture supports rebuilding without Python; the checks require actual quantum export records.

The SVG viewer displays the real H/RZ/RZZ/RX operations and measurements from the repository's two-layer circuit. Its downloadable Python constructs the same circuit. The browser computes energies classically and does not train a simulator or access quantum hardware. The penalty follows the Python score bound (57.65 at weight 0.25).

Scene anchors, wheel stops, waiting apron and exit are shared between build and motion. Departures clear the bay before arrivals; completed cars leave the scene. Motion pauses offscreen and when hidden, stops when settled, and snaps to the final state under reduced motion. Auto tour is opt-in.

Checks compare all 32 energies at 101 slider settings with the Python QUBO and Ising operators, preserve schedule/tie regressions, verify circuit exports and emitted JavaScript, and check geometry/projection invariants. The public Site identity remains in .openai/hosting.json.

## Independent circuit audit

Run `.venv/bin/python web/parking-anatomy/audit_circuit.py` from the repository root. It compares the full two-layer statevector with an independent QUBO-phase and tensor-product mixer calculation at 101 weights and three random angle sets, including reconstruction of the exported browser gate records. `check.mjs` verifies all six diagram stages, per-wire ordering, final measurements and a single linked symbol for each RZZ operation.

## Quantum contribution and benchmark evidence

Chapter 03 explains the charging-specific QUBO and hybrid workflow, credits standard QAOA, and traces exactly-one, shared-power and gun-conflict rules into the actual eight-qubit circuit. Chapter 04 embeds the offline benchmark report, exposes five cases, and downloads all per-run records.

Regenerate benchmarks separately from builds, in the Python project:

```sh
.venv/bin/python scripts/benchmark_quantum.py
```

The default report destination is `web/parking-anatomy/benchmark.json`. Copy that file into this Site checkout when working from the Sites source repository. Source hashes bind the report to the benchmark and solver implementations. Any source change requires rerunning the benchmark. Release builds must use the Python project explicitly:

```sh
PARKING_PYTHON=/absolute/project/.venv/bin/python \
PARKING_SOURCE_ROOT=/absolute/project PARKING_REQUIRE_PYTHON=1 node build.mjs
PARKING_PYTHON=/absolute/project/.venv/bin/python \
PARKING_SOURCE_ROOT=/absolute/project PARKING_REQUIRE_PYTHON=1 node build.mjs --light
node check.mjs
node check-shared.mjs
PARKING_SOURCE_ROOT=/absolute/project node check-benchmark.mjs
node motion-check.mjs
```

The exporter rejects stale or incomplete reports, mismatched inputs and answers not supported by raw observations. Builds do not rerun the full benchmark. Python-free builds may reuse the checked fixture only when the executable is absent; export or validation failures are fatal. The fixture and standalone report must match.

The current 150 workflows give QAOA 49/50 optimum hits, MILP 50/50 and structured random 50/50. MILP has lower median elapsed runtime in all five cases. The report includes CPU and wall timing, all final sample histograms, seeds, software versions, configurations, inputs and source hashes. See the Python project's `docs/quantum-benchmark.md` for boundaries and interpretation. No hardware jobs are submitted. The 60→45 minute illustration measures scheduling behavior and is never presented as quantum speedup.
