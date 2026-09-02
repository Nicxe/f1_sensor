#!/usr/bin/env python3
"""Validate Home Assistant translation key and placeholder parity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            flattened.update(_flatten(child, path))
        elif isinstance(child, str):
            flattened[path] = child
        else:
            raise ValueError(
                f"{path} must contain a string, got {type(child).__name__}"
            )
    return flattened


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations", type=Path)
    args = parser.parse_args()

    root = args.translations.resolve()
    english = _flatten(json.loads((root / "en.json").read_text(encoding="utf-8")))
    failures: list[str] = []
    for path in sorted(root.glob("*.json")):
        translated = _flatten(json.loads(path.read_text(encoding="utf-8")))
        missing = sorted(set(english) - set(translated))
        extra = sorted(set(translated) - set(english))
        if missing:
            failures.append(f"{path.name}: missing {', '.join(missing)}")
        if extra:
            failures.append(f"{path.name}: extra {', '.join(extra)}")
        for key in sorted(set(english) & set(translated)):
            expected = set(PLACEHOLDER_RE.findall(english[key]))
            actual = set(PLACEHOLDER_RE.findall(translated[key]))
            if expected != actual:
                failures.append(
                    f"{path.name}: {key} placeholders {sorted(actual)} != {sorted(expected)}"
                )

    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Translation parity passed: {len(english)} keys across {len(list(root.glob('*.json')))} locales"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
