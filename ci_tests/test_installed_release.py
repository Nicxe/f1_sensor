"""An externally supplied release must be smoke tested without rebuilding it."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts import test_installed_release


class InstalledReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.archive = Path(cls.directory.name) / "downloaded.zip"
        cls.version = "5.5.0-beta.99"
        subprocess.run(
            [
                sys.executable,
                "scripts/build_release.py",
                "--component",
                "custom_components/f1_sensor",
                "--output",
                str(cls.archive),
                "--version",
                cls.version,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def run_supplied_archive(self, returncode):
        original_bytes = self.archive.read_bytes()
        with zipfile.ZipFile(self.archive) as archive:
            expected_source = archive.read("__init__.py")

        def smoke(command, **kwargs):
            self.assertEqual(command[1:3], ["-m", "pytest"])
            component = Path(kwargs["env"]["F1_INSTALLED_ROOT"])
            self.assertNotEqual(component, Path.cwd() / "custom_components/f1_sensor")
            self.assertEqual((component / "__init__.py").read_bytes(), expected_source)
            manifest = json.loads((component / "manifest.json").read_text())
            self.assertEqual(manifest["version"], self.version)
            self.assertEqual(kwargs["env"]["PYTHONPATH"], str(component.parents[1]))
            return SimpleNamespace(returncode=returncode)

        with (
            patch.object(
                sys,
                "argv",
                [
                    "test_installed_release.py",
                    "--archive",
                    str(self.archive),
                    "--version",
                    self.version,
                ],
            ),
            patch.object(
                test_installed_release.subprocess, "run", side_effect=smoke
            ) as run,
        ):
            self.assertEqual(test_installed_release.main(), returncode)
        run.assert_called_once()
        self.assertEqual(self.archive.read_bytes(), original_bytes)

    def test_supplied_archive_is_extracted_and_never_rebuilt(self):
        self.run_supplied_archive(0)

    def test_installed_smoke_failure_is_not_hidden(self):
        self.run_supplied_archive(1)

    def test_wrong_version_is_rejected_before_running_ha(self):
        with (
            patch.object(
                sys,
                "argv",
                [
                    "test_installed_release.py",
                    "--archive",
                    str(self.archive),
                    "--version",
                    "5.5.1",
                ],
            ),
            patch.object(test_installed_release.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(ValueError, "version mismatch"):
                test_installed_release.main()
            run.assert_not_called()

    def test_missing_archive_cannot_fall_back_to_building(self):
        with (
            patch.object(
                sys,
                "argv",
                [
                    "test_installed_release.py",
                    "--archive",
                    str(self.archive.with_name("missing.zip")),
                ],
            ),
            patch.object(test_installed_release.subprocess, "run") as run,
        ):
            with self.assertRaises(FileNotFoundError):
                test_installed_release.main()
            run.assert_not_called()
