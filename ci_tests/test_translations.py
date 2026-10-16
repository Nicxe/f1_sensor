"""Tests for Weblate translation validation policy."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_translations import validate_translations


class TranslationValidationTests(unittest.TestCase):
    """Protect sparse locales while rejecting unsafe translation changes."""

    def _validate(self, files: dict[str, dict]) -> tuple[list[str], int]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in files.items():
                (root / name).write_text(
                    json.dumps(content, ensure_ascii=False), encoding="utf-8"
                )
            failures, _source_keys, _locale_count, untranslated = validate_translations(
                root
            )
        return failures, untranslated

    def test_sparse_locale_uses_english_fallback(self) -> None:
        failures, untranslated = self._validate(
            {
                "en.json": {"config": {"title": "Setup", "description": "Hi {name}"}},
                "sv.json": {"config": {"title": "Konfiguration"}},
            }
        )

        self.assertEqual(failures, [])
        self.assertEqual(untranslated, 1)

    def test_extra_key_is_rejected(self) -> None:
        failures, _ = self._validate(
            {
                "en.json": {"config": {"title": "Setup"}},
                "sv.json": {"config": {"title": "Konfiguration", "extra": "Fel"}},
            }
        )

        self.assertIn("sv.json: extra config.extra", failures)

    def test_placeholder_changes_and_blank_values_are_rejected(self) -> None:
        failures, _ = self._validate(
            {
                "en.json": {"config": {"description": "Hi {name}", "title": "Setup"}},
                "sv.json": {"config": {"description": "Hej {person}", "title": " "}},
            }
        )

        self.assertIn("sv.json: blank config.title", failures)
        self.assertIn(
            "sv.json: config.description placeholders ['person'] != ['name']",
            failures,
        )

    def test_non_string_leaf_is_rejected(self) -> None:
        failures, _ = self._validate(
            {
                "en.json": {"config": {"title": "Setup"}},
                "sv.json": {"config": {"title": ["Konfiguration"]}},
            }
        )

        self.assertEqual(
            failures,
            ["sv.json: config.title must contain a string, got list"],
        )

    def test_filename_must_use_bcp47_syntax(self) -> None:
        failures, _ = self._validate(
            {
                "en.json": {"config": {"title": "Setup"}},
                "pt_BR.json": {"config": {"title": "Configuração"}},
            }
        )

        self.assertIn("pt_BR.json: filename must use a BCP47 language tag", failures)


if __name__ == "__main__":
    unittest.main()
