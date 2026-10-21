#!/usr/bin/env python3
"""Catch deterministic Home Assistant manifest errors before remote hassfest."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_manifest(path: Path) -> list[str]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path}: {error}"]
    if not isinstance(manifest, dict):
        return [f"{path}: manifest must be an object"]
    keys = list(manifest)
    expected = ["domain", "name", *sorted(set(keys) - {"domain", "name"})]
    if keys != expected:
        return [
            f"{path}: keys must be domain, name, then the remaining keys alphabetically"
        ]
    return []


def main() -> int:
    errors = validate_manifest(ROOT / "custom_components/f1_sensor/manifest.json")
    print("\n".join(errors) if errors else "Home Assistant manifest ordering passed")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
