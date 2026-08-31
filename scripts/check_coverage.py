#!/usr/bin/env python3
"""Enforce the Phase 5 coverage ratchet without claiming the Silver target early."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _file_percent(files: dict[str, object], suffix: str) -> float | None:
    matches = [
        value
        for path, value in files.items()
        if path.replace("\\", "/").endswith(f"/f1_sensor/{suffix}")
    ]
    if len(matches) != 1:
        return None
    return float(matches[0]["summary"]["percent_covered"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("quality/coverage-ratchet.json"),
    )
    args = parser.parse_args()
    report = json.loads(args.coverage.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    failures: list[str] = []

    total = float(report["totals"]["percent_covered"])
    floor = float(config["global_floor"])
    if total + 0.001 < floor:
        failures.append(f"global coverage {total:.3f}% is below {floor:.3f}%")

    for module, module_floor in config["module_floors"].items():
        measured = _file_percent(report["files"], module)
        if measured is None:
            failures.append(f"coverage report does not contain {module}")
        elif measured + 0.001 < float(module_floor):
            failures.append(
                f"{module} coverage {measured:.3f}% is below {module_floor:.1f}%"
            )

    if failures:
        print("Coverage ratchet failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(
        f"Coverage ratchet passed at {total:.3f}%; next target is "
        f"{config['next_global_target']:.1f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
