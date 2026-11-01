# EV Scheduling Lab

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
