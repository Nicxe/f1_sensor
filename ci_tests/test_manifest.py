"""Catch manifest/import contract errors without replacing upstream hassfest."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_manifest import validate_manifest


class ManifestTests(unittest.TestCase):
    def test_required_prefix_and_alphabetical_remainder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for manifest, valid in (
                (
                    {
                        "domain": "f1_sensor",
                        "name": "F1 Sensor",
                        "dependencies": [],
                        "version": "1",
                    },
                    True,
                ),
                (
                    {
                        "domain": "f1_sensor",
                        "name": "F1 Sensor",
                        "version": "1",
                        "dependencies": [],
                    },
                    False,
                ),
                ({"name": "F1 Sensor", "domain": "f1_sensor"}, False),
                ({"version": "1"}, False),
                ([], False),
            ):
                path.write_text(json.dumps(manifest))
                self.assertEqual(not validate_manifest(path), valid)


class ComponentDependencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "manifest.json"
        self.manifest()

    def manifest(self, **fields):
        manifest = {"domain": "example_integration", "name": "Example", **fields}
        manifest = {
            key: manifest[key]
            for key in ("domain", "name", *sorted(set(manifest) - {"domain", "name"}))
        }
        self.path.write_text(json.dumps(manifest), encoding="utf-8")

    def source(self, code, filename="sensor.py"):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")

    def test_all_literal_import_forms_aliases_and_multiline_require_declaration(self):
        for code in (
            "import homeassistant.components.other_component.helpers as helper\n",
            "from homeassistant.components.other_component.const import (\n    VALUE as value,\n)\n",
            "from homeassistant.components import other_component as other\n",
        ):
            with self.subTest(code=code):
                self.source(code)
                errors = validate_manifest(self.path)
                self.assertEqual(len(errors), 1)
                self.assertIn("other_component", errors[0])
                self.assertIn("dependencies or after_dependencies", errors[0])

    def test_each_import_in_a_base_component_import_is_checked(self):
        self.source(
            "from homeassistant.components import other_component, another_component\n"
        )
        self.manifest(dependencies=["other_component"])
        errors = validate_manifest(self.path)
        self.assertEqual(len(errors), 1)
        self.assertIn("another_component", errors[0])

    def test_required_or_optional_declaration_satisfies_the_same_import_contract(self):
        self.source(
            "from homeassistant.components.other_component.const import VALUE\n"
        )
        for field in ("dependencies", "after_dependencies"):
            with self.subTest(field=field):
                self.manifest(**{field: ["other_component"]})
                self.assertEqual(validate_manifest(self.path), [])

    def test_standard_platform_internal_core_and_self_imports_are_not_false_positives(
        self,
    ):
        self.source(
            "import homeassistant.components.sensor as sensor\n"
            "from homeassistant.components import websocket_api, persistent_notification\n"
            "from homeassistant.components.example_integration.const import VALUE\n"
        )
        self.assertEqual(validate_manifest(self.path), [])

    def test_implemented_platforms_are_permitted_like_hassfest(self):
        self.source("from homeassistant.components.other_component import Entity\n")
        for filename in ("other_component.py", "other_component/__init__.py"):
            with self.subTest(filename=filename):
                self.source("", filename)
                self.assertEqual(validate_manifest(self.path), [])
                (self.root / filename).unlink()

    def test_nested_test_imports_are_scanned_as_well_as_runtime_files(self):
        self.source(
            "from homeassistant.components.other_component import State\n",
            "tests/nested/test_behavior.py",
        )
        errors = validate_manifest(self.path)
        self.assertEqual(len(errors), 1)
        self.assertIn("test_behavior.py", errors[0])
        self.assertIn("other_component", errors[0])

    def test_type_checking_imports_comments_and_strings_are_not_runtime_dependencies(
        self,
    ):
        self.source(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from homeassistant.components.other_component import State\n"
            "# from homeassistant.components.other_component import State\n"
            "description = 'import homeassistant.components.other_component'\n"
        )
        self.assertEqual(validate_manifest(self.path), [])
        self.source(
            "from homeassistant.components.other_component import State\n", "runtime.py"
        )
        self.assertTrue(validate_manifest(self.path))

    def test_syntax_errors_fail_closed_without_running_any_code(self):
        self.source("raise RuntimeError('integration code must never execute')\n")
        self.assertEqual(validate_manifest(self.path), [])
        self.source("def invalid(:\n")
        errors = validate_manifest(self.path)
        self.assertEqual(len(errors), 1)
        self.assertIn("could not inspect component imports", errors[0])

    def test_upstream_discovery_and_signed_path_exemptions_are_preserved(self):
        self.source(
            "from homeassistant.components.http.auth import async_sign_path as sign\n"
        )
        self.assertEqual(validate_manifest(self.path), [])
        self.source("from homeassistant.components import zeroconf, bluetooth\n")
        self.manifest(homekit=[{}], after_dependencies=["bluetooth_adapters"])
        self.assertEqual(validate_manifest(self.path), [])

    def test_invalid_manifest_structure_does_not_start_import_inspection(self):
        self.source("def invalid(:\n")
        for content in (
            "not JSON",
            "[]",
            '{"domain":"first","domain":"second","name":"Example"}',
        ):
            with self.subTest(content=content):
                self.path.write_text(content)
                errors = validate_manifest(self.path)
                self.assertTrue(errors)
                self.assertFalse(any("could not inspect" in error for error in errors))
        self.path.unlink()
        self.assertTrue(validate_manifest(self.path))

    def test_dependency_fields_reject_invalid_types_duplicates_and_overlap(self):
        for fields in (
            {"dependencies": "other_component"},
            {"after_dependencies": [None]},
            {"dependencies": [""]},
            {"dependencies": ["other_component", "other_component"]},
            {
                "dependencies": ["other_component"],
                "after_dependencies": ["other_component"],
            },
            {"domain": []},
            {"name": None},
        ):
            with self.subTest(fields=fields):
                self.manifest(**fields)
                self.assertTrue(validate_manifest(self.path))
