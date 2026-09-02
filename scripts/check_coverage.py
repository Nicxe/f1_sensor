#!/usr/bin/env python3
"""Enforce the Phase 5 coverage ratchet and completed Silver target."""

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


def _integration_modules(files: dict[str, object]) -> list[tuple[str, float]]:
    modules: list[tuple[str, float]] = []
    for path, value in files.items():
        normalized = path.replace("\\", "/")
        marker = "custom_components/f1_sensor/"
        if marker not in normalized or not normalized.endswith(".py"):
            continue
        relative = normalized.split(marker, 1)[1]
        if relative.startswith("tests/"):
            continue
        modules.append((relative, float(value["summary"]["percent_covered"])))
    return sorted(modules)


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
    require_above_floor = bool(config.get("require_above_global_floor", False))
    if require_above_floor and total <= floor:
        failures.append(f"global coverage {total:.3f}% must be above {floor:.3f}%")
    elif not require_above_floor and total + 0.001 < floor:
        failures.append(f"global coverage {total:.3f}% is below {floor:.3f}%")

    for module, module_floor in config["module_floors"].items():
        measured = _file_percent(report["files"], module)
        if measured is None:
            failures.append(f"coverage report does not contain {module}")
        elif measured + 0.001 < float(module_floor):
            failures.append(
                f"{module} coverage {measured:.3f}% is below {module_floor:.1f}%"
            )

    all_module_floor = config.get("all_module_floor")
    if all_module_floor is not None:
        module_floor = float(all_module_floor)
        require_above_module_floor = bool(
            config.get("require_above_all_module_floor", False)
        )
        modules = _integration_modules(report["files"])
        if not modules:
            failures.append("coverage report contains no integration modules")
        for module, measured in modules:
            below = (
                measured <= module_floor
                if require_above_module_floor
                else measured + 0.001 < module_floor
            )
            if below:
                relation = "above" if require_above_module_floor else "at least"
                failures.append(
                    f"{module} coverage {measured:.3f}% must be {relation} "
                    f"{module_floor:.1f}%"
                )

    if failures:
        print("Coverage ratchet failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    next_target = config.get("next_global_target")
    if next_target is None:
        print(
            f"Coverage ratchet passed at {total:.3f}%; the Silver target "
            f"of more than {floor:.1f}% globally and for every integration "
            "module is enforced"
        )
    else:
        print(
            f"Coverage ratchet passed at {total:.3f}%; next target is "
            f"{float(next_target):.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
