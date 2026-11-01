# Anatomy implementation brief

This is the comprehensive project brief given to the implementation sub-agent.
The user requested installation of Anatomy, followed by a sub-agent building a
simple webpage about the parking example and its future quantum scheduler.

## Scope and ownership

Work inside `web/parking-anatomy/`. Preserve the existing Python scheduler,
tests, dependency files, and user work. Build a small, accessible, responsive,
framework-free educational page, with a reproducible `build.mjs` producing
`dist/index.html`. Prefer a standalone page that also opens from a local file.
The parent agent handles private hosting, publication, and final browser review.
Do not create another Site, modify its hosting identity, or commit the main repo.
No paid services, accounts, API keys, map service, or backend are needed.

## Use Anatomy

Read the installed skill at `/Users/tsubasa/.codex/skills/anatomy/SKILL.md`,
its craft, kit, motion, and verification references, and a framework-free
example. Use the actual kit, preserve its MIT license, and vendor only what is
needed for a reproducible build.

Use the **Figure** tier: one recognizable miniature charging lot or physical
reservation instrument with roughly 40–80 purposeful parts. Write its concept
and grouped parts list before drawing. Show shaded solid cars, bays, chargers,
mountings, and precise details on a substantial base. Give the illustration a
framed title, interaction hint, live readout, and caption. Explain the mechanism
through the object; avoid a generic flowchart of boxes and arrows. Use calm
motion and correct depth order. Keep labels outside the drawing. Avoid WebGL
and complex moving geometry unless required by the explanation.

Support keyboard controls, focus states, useful text alternatives, light/dark
themes, reduced motion, and a 390 px mobile layout without horizontal overflow.
Follow applicable Anatomy capture, line, and geometry checks, inspect the PNGs,
and report any verification limits honestly.

## Project context

Read the repository's `README.md`, `main.py`, `src/ev_scheduler.py`, tests,
and `pyproject.toml`. This is an educational **EV charging scheduler**. Parking
bays are one-port charging stations. A booking reserves the full one-hour slot,
although charging can finish earlier.

The current milestone is classical: validate scenario → calculate travel and
arrival energy → generate individually feasible bookings → score them → search
all combinations selecting one booking per car → reject shared station/slot
conflicts → return the lowest total score. The exact solver is a trusted
baseline for future QUBO/QAOA experiments. Qiskit dependencies exist, but the
quantum scheduler is not integrated. A `script.py` mentioned in the README is
absent; do not invent its contents.

## Source scenario

| Input | Car A | Car B |
| --- | --- | --- |
| Battery capacity | 50 kWh | 50 kWh |
| Initial charge | 30% | 12% |
| Target charge | 50% | 30% |
| Consumption | 0.2 kWh/km | 0.2 kWh/km |
| Available | 07:45 | 07:50 |
| Deadline | 10:00 | 09:00 |
| North journey | 2 km / 10 min | 1 km / 5 min |
| South journey | 5 km / 15 min | 20 km / 30 min |

North and South each have one 11 kW port. Early is 08:00–09:00; late is
09:00–10:00. North tariffs are ₹2 and ₹1 per kWh; South tariffs are ₹3 and ₹2.
The arrival reserve is 5% of capacity, or 2.5 kWh. Default waiting weight is
0.25 points/minute. Cars depart as soon as available.

Calculate initial energy from capacity and charge percentage; subtract driving
energy; calculate arrival time; subtract arrival energy from the target to get
the charging energy. Duration is energy / power × 60 minutes. Check reserve,
arrival before slot start, actual completion before deadline, and energy fitting
the slot. Electricity bill is the required energy × tariff. Waiting is the
interval between arrival and slot start. **Score = bill + weight × waiting**;
score is in preference points, not rupees.

## The five feasible bookings

Use this stable order for the quantum encoding, verified against the generator:

| Bit | Booking | Energy | Bill | Wait | Default score |
| --- | --- | ---: | ---: | ---: | ---: |
| x0 | A / North / early | 10.4 kWh | ₹20.80 | 5 min | 22.05 |
| x1 | A / North / late | 10.4 kWh | ₹10.40 | 65 min | 26.65 |
| x2 | A / South / early | 11 kWh | ₹33.00 | 0 min | 33.00 |
| x3 | A / South / late | 11 kWh | ₹22.00 | 60 min | 37.00 |
| x4 | B / North / early | 9.2 kWh | ₹18.40 | 5 min | 19.65 |

B cannot use South: its arrival battery is 2 kWh, below reserve; arrival and
deadline rules also reject its bookings. B cannot use North late because of
its 09:00 deadline. Explain why giving A its individually cheapest scored
booking, North early, blocks B entirely.

The four one-per-car combinations are x0+x4 (conflict), x1+x4 (46.30),
x2+x4 (52.65), and x3+x4 (56.65). The default optimum is:

- B: North, reserve 08:00–09:00, charging completes about 08:50:11.
- A: North, reserve 09:00–10:00, charging completes about 09:56:44.
- Electricity ₹28.80; waiting 70 minutes; score 46.30; energy 19.6 kWh.
- Four combinations checked, three conflict-free combinations.

At waiting weight 1, the winner changes to A/South/early and B/North/early:
bill ₹51.40, wait 5 minutes, score 56.40. The crossover is near weight
0.3476923; ties retain original input order. Setting both chargers to 1 kW
makes the problem infeasible. Derive dynamic numbers from one model, preferably
using exported source data from Python. Useful controls include weight presets
0.25 and 1, a 0–1 weight slider, an early/late selector, a conflict demonstration,
and an encoding inspector. Avoid building unrelated features.

## Quantum explanation

Use five booking bits: 1 selects a booking and 0 skips it. In this unpruned
one-hot encoding, five qubits span 32 computational basis states. Only four
states choose exactly one booking for each car, and three are conflict-free.
Explicitly display bit order **x0 x1 x2 x3 x4, left to right**. The default
winner is `01001`; Qiskit often prints registers in a different order.

For this fixture and weight range 0–1, a sufficient penalty is P = 200:

```text
E(x) = Σ ci xi + P [(x0+x1+x2+x3−1)² + (x4−1)² + x0x4]
```

Explain the two one-booking-per-car penalties and the North/early conflict
penalty. Keep objective, penalty, and QUBO energy distinct. Compute all 32
energies if useful; do not fabricate quantum probabilities or measured counts.
`00000` has missing cars and `10001` double-books North early. Valid schedules
have zero penalty. The minimum is 46.30 at default preferences.

Describe the proposed hybrid workflow in plain language, with optional math:

1. Map each bit with xi = (1 − Zi)/2 into a cost Hamiltonian.
2. Initialize qubits in |+⟩ states with Hadamard gates.
3. Alternate cost evolution exp(−iγHC) and mixer exp(−iβΣX), for p layers.
4. A classical optimizer adjusts the angles using estimated energy.
5. Measure many shots, decode the booking bits, and validate constraints.
6. Compare the best feasible candidate with the checked classical baseline.

QAOA is approximate, may miss the optimum, and has no demonstrated speedup in
this example. Do not suggest measurement reveals every answer simultaneously.
Keep the four combinations checked by the classical solver distinct from the
32 states in the illustrative encoding. A real browser QAOA simulator is
optional and not needed. Label the current browser demonstration as classical
QUBO enumeration and the QAOA integration as proposed.

When researching technical claims, use primary sources such as IBM's official
QAOA tutorial, and include concise source links. The parent verified:
https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm

## Delivery and acceptance

Make one connected educational story: problem → greedy conflict → candidate
schedules → winning reservation board → quantum encoding and decoding. The
reader should understand what is scheduled, why A waits, where the five bits
come from, and how a measured bitstring becomes station/time assignments.
Use a clear title such as “Two cars. One charging plan.” and distinguish the
implemented classical solver from planned quantum work.

Deliver reproducible source, vendored required kit modules with license,
`dist/index.html`, and short build/preview instructions. Check JavaScript
syntax, model arithmetic, QUBO minimum, controls, desktop/mobile appearance,
and browser console. Report only checks actually run. The existing 20 Python
tests pass. Notify the parent when the first recognizable build is ready;
the parent will independently compare the browser model with Python, inspect
the live page, and publish the verified result privately.
