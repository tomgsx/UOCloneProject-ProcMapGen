#!/usr/bin/env python3
"""Check that a completed world folder is well-formed.

Usage:
    python3 tools/verify_release.py --world <world_dir> [--baseline <metrics.json>]

A world folder written by the app (or by the frozen app's --headless-world)
must contain every file in REQUIRED_OUTPUTS. A bare `python3 -m gen.pipeline`
run writes the same files except config.json and generation.log, which the
app's world task adds. With --baseline, the folder's metrics.json must also
equal the given one key for key, which is a quick way to confirm that a rebuilt
release still generates the same world (the byte-identical contract in
VERIFICATION.md is the stronger check: compare the MUL hashes).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_OUTPUTS = {
    "map0.mul",
    "staidx0.mul",
    "statics0.mul",
    "overview.png",
    "gen_state.npz",
    "meta.json",
    "metrics.json",
    "config.json",
    "generation.log",
}


def verify_world(world: Path, baseline: Path | None) -> list[str]:
    problems = []
    missing = REQUIRED_OUTPUTS - {path.name for path in world.iterdir()}
    if missing:
        problems.append(f"World output is missing: {', '.join(sorted(missing))}")
    if baseline and not missing:
        expected = json.loads(baseline.read_text(encoding="utf-8"))
        actual = json.loads((world / "metrics.json").read_text(encoding="utf-8"))
        if actual != expected:
            differing = sorted(
                key for key in set(expected) | set(actual) if expected.get(key) != actual.get(key)
            )
            problems.append(f"Metrics differ for: {', '.join(differing)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--world", type=Path, required=True, help="a completed world folder")
    parser.add_argument("--baseline", type=Path, help="a metrics.json the world must match exactly")
    args = parser.parse_args()
    problems = verify_world(args.world, args.baseline)
    if problems:
        print("\n".join(problems))
        return 1
    print("Release verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
