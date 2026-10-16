"""Regression tests for the local dev verification planner."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_dev  # noqa: E402


class VerifyDevTests(unittest.TestCase):
    def test_integration_change_matches_runtime_ci_checks(self) -> None:
        selected = verify_dev.select_jobs(
            ["custom_components/f1_sensor/coordinator.py"], {}, "push", "dev"
        )

        names = [name for name, _, _ in verify_dev.command_plan(selected)]

        self.assertEqual(
            ["lint", "backend", "frontend", "package", "automation"], names
        )

    def test_docs_change_avoids_runtime_suite(self) -> None:
        selected = verify_dev.select_jobs(
            ["docs/features/replay.md"], {}, "push", "dev"
        )

        names = [name for name, _, _ in verify_dev.command_plan(selected)]

        self.assertEqual(["documentation", "automation"], names)

    def test_backend_takes_precedence_over_blueprints(self) -> None:
        selected = verify_dev.select_jobs(
            ["custom_components/f1_sensor/coordinator.py"], {}, "push", "dev"
        )

        self.assertFalse(selected["blueprints"])


if __name__ == "__main__":
    unittest.main()
