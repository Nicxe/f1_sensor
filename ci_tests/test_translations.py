"""Tests for Weblate translation validation policy."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.check_translations import validate_translations


class TranslationValidationTests(unittest.TestCase):
    """Protect sparse locales while rejecting unsafe translation changes."""

    def _validate(
        self, files: dict[str, dict], *, flat: bool = False
    ) -> tuple[list[str], int]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in files.items():
                (root / name).write_text(
                    json.dumps(content, ensure_ascii=False), encoding="utf-8"
                )
            failures, _source_keys, _locale_count, untranslated = validate_translations(
                root, flat=flat
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

    def test_obsolete_keys_warn_without_blocking_legitimate_weblate_updates(
        self,
    ) -> None:
        for flat in (False, True):
            with (
                self.subTest(flat=flat),
                self.assertWarnsRegex(
                    UserWarning, "sv.json: obsolete translation keys ignored: removed"
                ),
            ):
                failures, missing = self._validate(
                    {
                        "en.json": {"title": "Setup", "new": "Hi {name}"},
                        "sv.json": {"title": "New wording", "removed": " "},
                        "cy.json": {},
                    },
                    flat=flat,
                )

                self.assertEqual(failures, [])
                self.assertEqual(missing, 3)

    def test_obsolete_keys_do_not_mask_broken_current_translations(self) -> None:
        with self.assertWarns(UserWarning):
            failures, _ = self._validate(
                {
                    "en.json": {"title": "Hi {name}"},
                    "sv.json": {"title": "Hej {person}", "removed": "Old"},
                }
            )
        self.assertEqual(
            failures, ["sv.json: title placeholders ['person'] != ['name']"]
        )

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

    def test_rewording_sparse_new_languages_and_repeated_placeholders_are_safe(
        self,
    ) -> None:
        for flat in (False, True):
            with self.subTest(flat=flat):
                failures, missing = self._validate(
                    {
                        "en.json": {"title": "Hello {name}", "fallback": "Source"},
                        "sv.json": {
                            "title": "{name}, a completely different phrase, {name}"
                        },
                        "de.json": {"title": "A newly translated {name}"},
                        "pt-BR.json": {},
                    },
                    flat=flat,
                )
                self.assertEqual(failures, [])
                self.assertEqual(missing, 4)

    def test_flat_catalog_rejects_nested_messages(self) -> None:
        failures, _ = self._validate(
            {
                "en.json": {"card.title": "Source"},
                "sv.json": {"card": {"title": "Text"}},
            },
            flat=True,
        )
        self.assertEqual(failures, ["sv.json: card must contain a string, got dict"])

    def test_duplicate_keys_invalid_json_and_non_objects_have_actionable_errors(
        self,
    ) -> None:
        for content, message in (
            ('{"title":"first","title":"second"}', "duplicate JSON key 'title'"),
            (
                '{"config":{"title":"first","title":"second"}}',
                "duplicate JSON key 'title'",
            ),
            ("[]", "catalog must be an object"),
            ("{", "Expecting property name"),
        ):
            with self.subTest(content=content), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "en.json").write_text('{"title":"Source"}', encoding="utf-8")
                (root / "sv.json").write_text(content, encoding="utf-8")
                failures, *_ = validate_translations(root)
                self.assertEqual(len(failures), 1)
                self.assertTrue(failures[0].startswith("sv.json: "))
                self.assertIn(message, failures[0])

    def test_source_is_required_and_nonempty_and_locale_names_are_unique(self) -> None:
        for files in ({}, {"en.json": {}}):
            with self.subTest(files=files):
                failures, _ = self._validate(files)
                self.assertTrue(failures[0].startswith("en.json: "))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "en.json").write_text('{"title":"Source"}', encoding="utf-8")
            (root / "pt-BR.json").write_text("{}", encoding="utf-8")
            (root / "pt-br.json").write_text("{}", encoding="utf-8")
            # Simulate case-distinct filenames also on case-insensitive macOS disks.
            with patch.object(
                Path,
                "glob",
                return_value=[
                    root / name for name in ("en.json", "pt-BR.json", "pt-br.json")
                ],
            ):
                failures, *_ = validate_translations(root)
            self.assertIn("pt-br.json: duplicates language in pt-BR.json", failures)


if __name__ == "__main__":
    unittest.main()
