"""Stale local installations must not serve as evidence for a different lock."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ci_environment


class EnvironmentTests(unittest.TestCase):
    def test_postinstall_patch_changes_invalidate_dependency_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ci_environment.NPM_INPUTS:
                (root / name).write_text("unchanged")
            patches = root / "patches"
            patches.mkdir()
            patch_file = patches / "dependency.patch"
            patch_file.write_text("old patch")
            with patch.object(ci_environment, "ROOT", root):
                original = ci_environment.digest_files(
                    ci_environment.npm_install_inputs()
                )
                patch_file.write_text("new patch")
                changed = ci_environment.digest_files(
                    ci_environment.npm_install_inputs()
                )
                self.assertNotEqual(original, changed)
                patch_file.unlink()
                removed = ci_environment.digest_files(
                    ci_environment.npm_install_inputs()
                )
                self.assertNotEqual(changed, removed)
                (root / ".npmrc").write_text("ignore-scripts=true")
                self.assertNotEqual(
                    removed,
                    ci_environment.digest_files(ci_environment.npm_install_inputs()),
                )

    def test_environment_drift_and_wrong_tools_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stamp = root / "environment.json"
            stamp.write_text(json.dumps({"dependencies": {"lock": "old"}}))
            binary = root / "bin/actionlint"
            binary.parent.mkdir()
            binary.touch()
            browser = root / "chromium"
            browser.touch()
            with (
                patch.object(ci_environment, "STAMP", stamp),
                patch.object(ci_environment, "TOOLS", root),
                patch.object(
                    ci_environment,
                    "expected_versions",
                    return_value={"node": "v22", "npm": "10", "python": "3.14"},
                ),
                patch.object(
                    ci_environment,
                    "installed_versions",
                    return_value={"node": "v26", "npm": "11", "python": "3.14"},
                ),
                patch.object(
                    ci_environment,
                    "dependency_fingerprints",
                    return_value={"lock": "new"},
                ),
                patch.object(ci_environment, "output", return_value=str(browser)),
            ):
                errors = ci_environment.environment_errors()
                self.assertTrue(any("node:" in error for error in errors))
                self.assertTrue(any("npm:" in error for error in errors))
                self.assertTrue(any("dependencies" in error for error in errors))

    def test_missing_setup_is_not_a_clean_environment(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(ci_environment, "STAMP", Path(directory) / "missing"),
        ):
            self.assertTrue(ci_environment.environment_errors())
