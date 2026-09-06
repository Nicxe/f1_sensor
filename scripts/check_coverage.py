#!/usr/bin/env python3
"""Require strictly over 95% runtime line coverage globally and per module."""

import argparse
import json
import math
from pathlib import Path


def _line_counts(summary: dict, label: str) -> tuple[int, int]:
    if not isinstance(summary, dict):
        raise ValueError(f"missing runtime line counts: {label}")
    statements = summary.get("num_statements")
    covered = summary.get("covered_lines")
    if (
        type(statements) is not int
        or type(covered) is not int
        or not 0 <= covered <= statements
    ):
        raise ValueError(f"invalid runtime line counts: {label}")
    return statements, covered


def coverage_measurements(report: dict) -> tuple[float, dict[str, float]]:
    if not isinstance(report, dict):
        raise ValueError("coverage report must be an object")
    statements, covered = _line_counts(report.get("totals"), "totals")
    files = report.get("files")
    if not statements or not isinstance(files, dict) or not files:
        raise ValueError("coverage report contains no runtime modules or statements")
    modules: dict[str, float] = {}
    module_statements = module_covered = 0
    for filename, data in files.items():
        if "/tests/" in filename.replace("\\", "/"):
            raise ValueError("test helpers must not be included in runtime coverage")
        if not isinstance(data, dict):
            raise ValueError(f"invalid runtime module evidence: {filename}")
        count, hit = _line_counts(data.get("summary"), filename)
        module_statements += count
        module_covered += hit
        modules[filename] = 100 * hit / count if count else 100.0
    if (module_statements, module_covered) != (statements, covered):
        raise ValueError("runtime module counts do not match report totals")
    return 100 * covered / statements, modules


def line_coverage(report: dict) -> float:
    return coverage_measurements(report)[0]


def _floor(config: dict, key: str) -> float:
    floor = config[key]
    if (
        isinstance(floor, bool)
        or not isinstance(floor, (int, float))
        or not math.isfinite(floor)
        or not 95 <= floor < 100
    ):
        raise ValueError(f"{key} must be at least 95 and below 100 percent")
    return floor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("quality/coverage-ratchet.json")
    )
    args = parser.parse_args()
    try:
        report = json.loads(args.coverage.read_text())
        config = json.loads(args.config.read_text())
        global_floor = _floor(config, "global_floor")
        module_floor = _floor(config, "module_floor")
        measured, modules = coverage_measurements(report)
    except (KeyError, TypeError, ValueError, OSError) as err:
        print(f"Invalid runtime coverage evidence: {err}")
        return 2
    print(f"Runtime line coverage: {measured:.3f}% (required: >{global_floor:.1f}%)")
    failures = []
    if measured <= global_floor:
        failures.append("global runtime line coverage does not exceed its floor")
    for filename, percentage in sorted(modules.items()):
        if percentage <= module_floor:
            failures.append(
                f"{filename}: {percentage:.3f}% (required: >{module_floor:.1f}%)"
            )
    if failures:
        print("Coverage gate failed:\n" + "\n".join(failures))
    else:
        print(f"All {len(modules)} runtime modules exceed {module_floor:.1f}%")
    totals = report["totals"]
    if totals.get("num_branches"):
        print(
            f"Branches covered: {totals['covered_branches']}/{totals['num_branches']} (informational)"
        )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
