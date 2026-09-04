#!/usr/bin/env python3
"""Require 95% runtime line coverage; report branches without a second gate."""

import argparse
import json
from pathlib import Path


def line_coverage(report: dict) -> float:
    totals = report["totals"]
    statements = totals["num_statements"]
    if statements <= 0:
        raise ValueError("coverage report contains no runtime statements")
    for filename in report["files"]:
        if "/tests/" in filename.replace("\\", "/"):
            raise ValueError("test helpers must not be included in runtime coverage")
    return 100 * totals["covered_lines"] / statements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("quality/coverage-ratchet.json")
    )
    args = parser.parse_args()
    report = json.loads(args.coverage.read_text())
    floor = json.loads(args.config.read_text())["global_floor"]
    measured = line_coverage(report)
    print(f"Runtime line coverage: {measured:.3f}% (required: {floor:.1f}%)")
    totals = report["totals"]
    if totals.get("num_branches"):
        print(
            f"Branches covered: {totals['covered_branches']}/{totals['num_branches']} (informational)"
        )
    return int(measured + 0.001 < floor)


if __name__ == "__main__":
    raise SystemExit(main())
