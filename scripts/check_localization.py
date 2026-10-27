#!/usr/bin/env python3
"""Validate both delivered Weblate catalogs with the same safety policy."""

from pathlib import Path

from check_translations import validate_translations

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "f1_sensor"


def main() -> int:
    failures = []
    for name, path, flat in (
        ("Integration", ROOT / "translations", False),
        (
            "Live data card",
            ROOT / "www" / "f1-sensor-live-data-card" / "localization" / "locales",
            True,
        ),
    ):
        errors, keys, locales, missing = validate_translations(path, flat=flat)
        failures.extend(f"{name}: {error}" for error in errors)
        print(
            f"{name}: {keys} source keys, {locales} locales, {missing} English fallbacks"
        )
    if failures:
        print("\n".join(failures))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
