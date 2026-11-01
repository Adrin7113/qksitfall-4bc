#!/usr/bin/env python3
"""Run the approved benchmark offline; website builds only consume its JSON."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.quantum_benchmark import run_benchmark, validate_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "web/parking-anatomy/benchmark.json")
    args = parser.parse_args()
    def progress(case, seed, runs):
        outcomes = ", ".join(f"{r['method']}={r['status']}" for r in runs)
        print(f"{case} · seed {seed}: {outcomes}", flush=True)
    report = run_benchmark(progress=progress)
    validate_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(args.output)
    print(f"Saved {len(report['cases'])} cases and 150 measured workflows to {args.output}")


if __name__ == "__main__":
    main()
