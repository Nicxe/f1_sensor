#!/usr/bin/env python3
"""Validate translator-owned catalogs without freezing wording or completeness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any
import warnings

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")
LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def read_catalog(path: Path, *, flat: bool = False) -> dict[str, str]:
    """Read JSON with duplicate detection and the component's message schema."""
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    if not isinstance(value, dict):
        raise ValueError("catalog must be an object")
    if flat:
        for key, message in value.items():
            if not isinstance(message, str):
                raise ValueError(
                    f"{key} must contain a string, got {type(message).__name__}"
                )
        return value
    return _flatten(value)


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


def validate_translations(
    root: Path, *, flat: bool = False
) -> tuple[list[str], int, int, int]:
    """Return validation failures and source/locale/untranslated counts."""
    failures: list[str] = []
    source_path = root / "en.json"
    try:
        english = read_catalog(source_path, flat=flat)
    except (json.JSONDecodeError, OSError, ValueError) as err:
        return [f"en.json: {err}"], 0, 0, 0
    if not english:
        return ["en.json: source catalog must not be empty"], 0, 0, 0

    untranslated = 0
    paths = sorted(root.glob("*.json"))
    filenames: dict[str, str] = {}
    for path in paths:
        if not LANGUAGE_TAG_RE.fullmatch(path.stem):
            failures.append(f"{path.name}: filename must use a BCP47 language tag")
        normalized = path.stem.lower()
        if normalized in filenames:
            failures.append(
                f"{path.name}: duplicates language in {filenames[normalized]}"
            )
        filenames[normalized] = path.name
        try:
            translated = read_catalog(path, flat=flat)
        except (json.JSONDecodeError, OSError, ValueError) as err:
            failures.append(f"{path.name}: {err}")
            continue
        missing = sorted(set(english) - set(translated))
        extra = sorted(set(translated) - set(english))
        if path != source_path:
            untranslated += len(missing)
        if extra:
            warnings.warn(
                f"{path.name}: obsolete translation keys ignored: {', '.join(extra)}",
                stacklevel=2,
            )
        blank = sorted(
            key
            for key, value in translated.items()
            if key in english and not value.strip()
        )
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
    parser.add_argument(
        "--flat", action="store_true", help="Validate flat card messages"
    )
    args = parser.parse_args()

    failures, source_keys, locale_count, untranslated = validate_translations(
        args.translations.resolve(), flat=args.flat
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
