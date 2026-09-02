#!/usr/bin/env python3
"""Fill missing custom-integration translations with explicit English fallbacks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _merge_fallbacks(
    target: dict[str, Any], source: dict[str, Any], prefix: str = ""
) -> list[str]:
    added: list[str] = []
    for key, value in source.items():
        path = f"{prefix}.{key}" if prefix else key
        if key not in target:
            target[key] = value
            added.append(path)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            added.extend(_merge_fallbacks(target[key], value, path))
    return added


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations", type=Path)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()

    translations = args.translations.resolve()
    english = json.loads((translations / "en.json").read_text(encoding="utf-8"))
    recorded = (
        json.loads(args.record.read_text(encoding="utf-8"))
        if args.record.exists()
        else {
            "policy": "Missing locale keys intentionally use the English source text until translated.",
            "locales": {},
        }
    )

    for path in sorted(translations.glob("*.json")):
        if path.name == "en.json":
            continue
        content = json.loads(path.read_text(encoding="utf-8"))
        added = _merge_fallbacks(content, english)
        if added:
            recorded.setdefault("locales", {}).setdefault(path.stem, [])
            recorded["locales"][path.stem] = sorted(
                set(recorded["locales"][path.stem]) | set(added)
            )
            path.write_text(
                json.dumps(content, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(
        json.dumps(recorded, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
