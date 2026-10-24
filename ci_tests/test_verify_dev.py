"""Regression tests for the local dev verification planner."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_dev  # noqa: E402


class VerifyDevTests(unittest.TestCase):
    def test_shared_lint_checks_root_test_fixtures(self) -> None:
        selected = verify_dev.select_jobs(["conftest.py"], {}, "push", "dev")
        lint_commands = {
            name: commands for name, commands, _ in verify_dev.command_plan(selected)
        }["lint"]
        for command in lint_commands:
            with self.subTest(command=command):
                self.assertIn("conftest.py", command)

    def test_integration_change_matches_runtime_ci_checks(self) -> None:
        selected = verify_dev.select_jobs(
            ["custom_components/f1_sensor/coordinator.py"], {}, "push", "dev"
        )

        names = [name for name, _, _ in verify_dev.command_plan(selected)]

        self.assertEqual(
            ["lint", "backend", "frontend", "translations", "package"], names
        )

    def test_docs_change_avoids_runtime_suite(self) -> None:
        selected = verify_dev.select_jobs(
            ["docs/features/replay.md"], {}, "push", "dev"
        )

        names = [name for name, _, _ in verify_dev.command_plan(selected)]

        self.assertEqual(["documentation"], names)

    def test_backend_takes_precedence_over_blueprints(self) -> None:
        selected = verify_dev.select_jobs(
            ["custom_components/f1_sensor/coordinator.py"], {}, "push", "dev"
        )

        self.assertFalse(selected["blueprints"])

    def test_full_profile_keeps_audit_and_workflow_validation(self) -> None:
        selected = verify_dev.select_jobs(None, {}, "workflow_dispatch", "dev")
        plan = verify_dev.command_plan(selected)
        self.assertIn("audit", [name for name, _, _ in plan])
        commands = {name: commands for name, commands, _ in plan}
        self.assertIn(
            [verify_dev.ci_python(), "scripts/setup_actionlint.py"],
            commands["automation"],
        )

    def test_invalid_base_is_an_error_not_an_empty_changeset(self) -> None:
        with patch(
            "verify_dev.subprocess.run",
            return_value=Mock(returncode=1, stderr=b"unknown ref"),
        ):
            with self.assertRaisesRegex(ValueError, "Git comparison"):
                verify_dev.changed_files("does-not-exist")

    def test_no_changes_never_produces_a_verification_receipt(self) -> None:
        with (
            patch.object(sys, "argv", ["verify_dev.py", "changed"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.changed_files", return_value=[]),
            patch("verify_dev.run") as execute,
        ):
            self.assertEqual(verify_dev.main(), 3)
            execute.assert_not_called()

    def test_print_plan_does_not_set_up_or_execute_any_checks(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                ["verify_dev.py", "release", "--target", "beta", "--print-plan"],
            ),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors") as environment,
            patch("verify_dev.run", return_value=0) as execute,
        ):
            self.assertEqual(verify_dev.main(), 0)
            environment.assert_not_called()
            self.assertTrue(execute.call_args.kwargs["print_only"])
            self.assertIn("audit", [name for name, _, _ in execute.call_args.args[0]])

    def test_invalid_base_invalidates_a_previous_success_receipt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "changed", "--base", "bad"]),
            patch("verify_dev.source_fingerprint", return_value="snapshot"),
            patch("verify_dev.resolve_base", side_effect=ValueError("invalid base")),
        ):
            receipt = Path(directory) / "test-results/verification.json"
            receipt.parent.mkdir()
            receipt.write_text('{"status":"local_passed_remote_pending"}')
            self.assertEqual(verify_dev.main(), 2)
            self.assertEqual(json.loads(receipt.read_text())["status"], "failed")

    def test_local_commands_use_ci_mode_and_isolated_tools(self) -> None:
        with (
            patch.dict("os.environ", {"F1_VISUAL_REVIEW": "1", "F1_MAINTENANCE": "1"}),
            patch(
                "verify_dev.subprocess.run", return_value=Mock(returncode=0)
            ) as execute,
        ):
            self.assertEqual(
                verify_dev.run(
                    [("example", [["node", "example.js"]], {})], print_only=False
                ),
                0,
            )
            environment = execute.call_args.kwargs["env"]
            self.assertEqual(environment["CI"], "true")
            self.assertTrue(
                environment["PATH"].startswith(str(verify_dev.PYTHON.parent))
            )
            self.assertEqual(environment["F1_BROWSER"], "chromium")
            self.assertEqual(environment["PYTEST_ADDOPTS"], "")
            self.assertEqual(environment["F1_MAINTENANCE"], "")
            self.assertEqual(environment["F1_VISUAL_REVIEW"], "")

    def test_selected_failures_are_all_reported_without_omitting_later_checks(
        self,
    ) -> None:
        results = []
        with patch(
            "verify_dev.subprocess.run",
            side_effect=[Mock(returncode=1), Mock(returncode=2), Mock(returncode=0)],
        ) as execute:
            self.assertEqual(
                verify_dev.run(
                    [
                        ("lint", [["lint"], ["format"]], {}),
                        ("backend", [["test"]], {}),
                    ],
                    print_only=False,
                    results=results,
                ),
                1,
            )
        self.assertEqual(execute.call_count, 3)
        self.assertEqual(
            [(item["name"], item["status"]) for item in results],
            [("lint", "failed"), ("backend", "passed")],
        )

    def test_failed_attempt_receipt_keeps_each_selected_result_and_source(self) -> None:
        def execute(plan, *, print_only, results):
            self.assertFalse(print_only)
            results.extend(
                {"name": name, "status": "failed" if name == "lint" else "passed"}
                for name, _, _ in plan
            )
            return 1

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "full"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors", return_value=[]),
            patch("verify_dev.source_fingerprint", return_value="snapshot"),
            patch("verify_dev.run", side_effect=execute),
            patch("verify_dev.installed_versions", return_value={"node": "pinned"}),
            patch(
                "verify_dev.dependency_fingerprints", return_value={"lock": "installed"}
            ),
        ):
            self.assertEqual(verify_dev.main(), 1)
            receipt = json.loads(
                (Path(directory) / "test-results/verification.json").read_text()
            )
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["source"], "snapshot")
            self.assertEqual(len(receipt["results"]), len(receipt["checks"]))
            self.assertIn({"name": "lint", "status": "failed"}, receipt["results"])
            self.assertIn({"name": "audit", "status": "passed"}, receipt["results"])

    def test_source_change_invalidates_earlier_success(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "full"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors", return_value=[]),
            patch(
                "verify_dev.source_fingerprint",
                side_effect=["before", "before", "after"],
            ),
            patch("verify_dev.run", return_value=0),
            patch("verify_dev.installed_versions", return_value={}),
            patch("verify_dev.dependency_fingerprints", return_value={}),
        ):
            receipt = Path(directory) / "test-results/verification.json"
            receipt.parent.mkdir()
            receipt.write_text('{"status":"local_passed_remote_pending"}')
            self.assertEqual(verify_dev.main(), 2)
            self.assertNotEqual(
                json.loads(receipt.read_text())["status"], "local_passed_remote_pending"
            )

    def test_source_change_during_setup_invalidates_selected_groups(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "changed"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.changed_files", return_value=["docs/example.md"]),
            patch("verify_dev.environment_errors", side_effect=[["stale"], []]),
            patch("verify_dev.subprocess.run", return_value=Mock(returncode=0)),
            patch(
                "verify_dev.source_fingerprint",
                side_effect=["docs-only", "backend-added"],
            ),
            patch("verify_dev.run") as execute,
        ):
            self.assertEqual(verify_dev.main(), 2)
            execute.assert_not_called()
            receipt = json.loads(
                (Path(directory) / "test-results/verification.json").read_text()
            )
            self.assertEqual(receipt["status"], "failed")

    def test_setup_failure_cannot_leave_a_running_or_success_receipt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "full"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors", return_value=["setup missing"]),
            patch("verify_dev.source_fingerprint", return_value="snapshot"),
            patch("verify_dev.subprocess.run", return_value=Mock(returncode=1)),
            patch("verify_dev.run") as execute,
        ):
            self.assertEqual(verify_dev.main(), 2)
            execute.assert_not_called()
            receipt = json.loads(
                (Path(directory) / "test-results/verification.json").read_text()
            )
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("setup failed", receipt["error"])

    def test_success_binds_receipt_to_source_profile_and_installed_dependencies(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "release", "--target", "beta"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors", return_value=[]),
            patch("verify_dev.source_fingerprint", return_value="snapshot"),
            patch("verify_dev.run", return_value=0),
            patch("verify_dev.installed_versions", return_value={"node": "pinned"}),
            patch(
                "verify_dev.dependency_fingerprints", return_value={"lock": "installed"}
            ),
        ):
            self.assertEqual(verify_dev.main(), 0)
            receipt = json.loads(
                (Path(directory) / "test-results/verification.json").read_text()
            )
            self.assertEqual(receipt["source"], "snapshot")
            self.assertEqual(receipt["target"], "beta")
            self.assertEqual(receipt["dependencies"], {"lock": "installed"})
            self.assertIn("audit", receipt["checks"])
            self.assertTrue(receipt["remote_confirmation"])

    def test_fingerprint_detects_content_and_deletion(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch("verify_dev.git_paths", return_value={"source.js"}),
        ):
            path = Path(directory) / "source.js"
            path.write_text("first")
            first = verify_dev.source_fingerprint()
            path.write_text("second")
            second = verify_dev.source_fingerprint()
            path.unlink()
            self.assertNotEqual(first, second)
            self.assertNotEqual(second, verify_dev.source_fingerprint())

    def test_dependency_change_during_run_invalidates_success(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("verify_dev.ROOT", Path(directory)),
            patch.object(sys, "argv", ["verify_dev.py", "full"]),
            patch("verify_dev.resolve_base", return_value="a" * 40),
            patch("verify_dev.environment_errors", return_value=[]),
            patch("verify_dev.source_fingerprint", return_value="snapshot"),
            patch("verify_dev.run", return_value=0),
            patch("verify_dev.installed_versions", return_value={}),
            patch(
                "verify_dev.dependency_fingerprints",
                side_effect=[{"lock": "before"}, {"lock": "after"}],
            ),
        ):
            self.assertEqual(verify_dev.main(), 2)
            receipt = json.loads(
                (Path(directory) / "test-results/verification.json").read_text()
            )
            self.assertNotEqual(receipt["status"], "local_passed_remote_pending")


if __name__ == "__main__":
    unittest.main()
