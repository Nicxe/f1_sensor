#!/usr/bin/env python3
"""Validate Weblate-managed Home Assistant translation files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")
LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


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


def validate_translations(root: Path) -> tuple[list[str], int, int, int]:
    """Return validation failures and source/locale/untranslated counts."""
    failures: list[str] = []
    source_path = root / "en.json"
    try:
        english = _flatten(json.loads(source_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, ValueError) as err:
        return [f"en.json: {err}"], 0, 0, 0

    untranslated = 0
    paths = sorted(root.glob("*.json"))
    for path in sorted(root.glob("*.json")):
        if not LANGUAGE_TAG_RE.fullmatch(path.stem):
            failures.append(f"{path.name}: filename must use a BCP47 language tag")
        try:
            translated = _flatten(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError) as err:
            failures.append(f"{path.name}: {err}")
            continue
        missing = sorted(set(english) - set(translated))
        extra = sorted(set(translated) - set(english))
        if path != source_path:
            untranslated += len(missing)
        if extra:
            failures.append(f"{path.name}: extra {', '.join(extra)}")
        blank = sorted(key for key, value in translated.items() if not value.strip())
        if blank:
            failures.append(f"{path.name}: blank {', '.join(blank)}")
        for key in sorted(set(english) & set(translated)):
            expected = set(PLACEHOLDER_RE.findall(english[key]))
            actual = set(PLACEHOLDER_RE.findall(translated[key]))
            if expected != actual:
                failures.append(
                    f"{path.name}: {key} placeholders {sorted(actual)} != {sorted(expected)}"
                )

    return failures, len(english), len(paths), untranslated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations", type=Path)
    args = parser.parse_args()

    failures, source_keys, locale_count, untranslated = validate_translations(
        args.translations.resolve()
    )

    if failures:
        raise SystemExit("\n".join(failures))
    print(
        "Translation validation passed: "
        f"{source_keys} source keys across {locale_count} locales; "
        f"{untranslated} untranslated values use the English fallback"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
