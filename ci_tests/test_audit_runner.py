"""Retry transport failures, but never retry away a genuine policy failure."""

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.check_npm_audit import match_advisory_versions, project_npm_cli
from scripts.run_npm_audit import read_baseline, run_audit as run_with_lock

LOCK = {
    "lockfileVersion": 3,
    "packages": {"": {}, "node_modules/pkg": {"version": "1.0.0"}},
}


def run_audit(*args, **kwargs):
    kwargs.setdefault("read_lock", lambda: LOCK)
    return run_with_lock(*args, **kwargs)


def result(vulnerabilities=None):
    vulnerabilities = {
        name: {"severity": "high", "nodes": [f"node_modules/{name}"], **details}
        for name, details in (vulnerabilities or {}).items()
    }
    for details in vulnerabilities.values():
        details["via"] = [{"range": "*", **item} for item in details["via"]]
    return SimpleNamespace(
        returncode=1 if vulnerabilities else 0,
        stdout=json.dumps(
            {
                "auditReportVersion": 2,
                "vulnerabilities": vulnerabilities,
                "metadata": {"vulnerabilities": {"total": len(vulnerabilities)}},
            }
        ),
    )


class RunnerTests(unittest.TestCase):
    def test_nested_npm_run_uses_same_pinned_cli_for_registry_and_semver(self):
        root = Path(__file__).resolve().parents[1]
        private = project_npm_cli()
        selected = []

        def execute(command, **kwargs):
            self.assertEqual(command[:3], ["node", str(private), "audit"])
            selected.append(Path(command[1]))
            return result({"pkg": {"via": [{"source": 42, "range": "<1.1.0"}]}})

        def match_versions(records, *, npm_cli):
            self.assertEqual(npm_cli, private)
            selected.append(npm_cli)
            return match_advisory_versions(records, npm_cli=npm_cli)

        with (
            patch.dict(
                os.environ,
                {
                    "npm_execpath": str(root / "node_modules/npm/bin/npm-cli.js"),
                    "PATH": str(root / "node_modules/.bin")
                    + os.pathsep
                    + os.environ["PATH"],
                },
            ),
            patch(
                "scripts.run_npm_audit.match_advisory_versions",
                side_effect=match_versions,
            ),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(run_audit({"entries": []}, execute, Mock()), 1)
        self.assertEqual(selected, [private, private])

    def test_timeout_empty_json_and_registry_errors_fail_after_bounded_retries(self):
        for result in [
            subprocess.TimeoutExpired("npm", 45),
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=1, stdout="not json"),
            SimpleNamespace(returncode=1, stdout='{"error":{"code":"E503"}}'),
        ]:
            run = (
                Mock(side_effect=result)
                if isinstance(result, Exception)
                else Mock(return_value=result)
            )
            sleep = Mock()
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(run_audit({"entries": []}, run, sleep), 2)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertNotIn("stale exception", output.getvalue())

    def test_valid_reports_have_distinct_pass_and_policy_failure_status(self):
        for vulnerabilities, status in [
            ({}, 0),
            ({"pkg": {"via": [{"source": 42}]}}, 1),
        ]:
            run = Mock(return_value=result(vulnerabilities))
            with redirect_stdout(StringIO()):
                self.assertEqual(run_audit({"entries": []}, run, Mock()), status)
            self.assertEqual(run.call_count, 1)

    def test_introduced_risk_uses_isolated_base_lock_without_installing_or_running_code(
        self,
    ):
        directories = []
        finding = {"pkg": {"via": [{"source": 42}]}}

        def execute(command, **kwargs):
            self.assertEqual(command[0], "node")
            self.assertEqual(command[2], "audit")
            self.assertIn("--package-lock-only", command)
            self.assertIn("--ignore-scripts", command)
            if "--prefix" in command:
                directory = Path(command[command.index("--prefix") + 1])
                self.assertEqual(
                    {path.name for path in directory.iterdir()},
                    {"package.json", "package-lock.json"},
                )
                directories.append(directory)
            return result(finding)

        base = Mock(
            return_value={"package.json": "{}", "package-lock.json": json.dumps(LOCK)}
        )
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                run_audit(
                    {"entries": []},
                    execute,
                    Mock(),
                    mode="introduced",
                    base="base-sha",
                    read_base=base,
                ),
                0,
            )
        base.assert_called_once_with("base-sha")
        self.assertTrue(all(not path.exists() for path in directories))
        self.assertIn("existing pkg", output.getvalue())

    def test_new_severe_advisory_blocks_without_retrying_away_the_finding(self):
        execute = Mock(
            side_effect=[result(), result({"pkg": {"via": [{"source": 42}]}})]
        )
        base = Mock(
            return_value={"package.json": "{}", "package-lock.json": json.dumps(LOCK)}
        )
        sleep = Mock()
        with redirect_stdout(StringIO()):
            self.assertEqual(
                run_audit(
                    {"entries": []},
                    execute,
                    sleep,
                    mode="introduced",
                    base="base-sha",
                    read_base=base,
                ),
                1,
            )
        self.assertEqual(execute.call_count, 2)
        sleep.assert_not_called()

    def test_both_base_and_current_registry_reports_are_required(self):
        unavailable = SimpleNamespace(returncode=1, stdout='{"error":{"code":"E503"}}')
        for reports, count in (
            ([unavailable] * 3, 3),
            ([result()] + [unavailable] * 3, 4),
        ):
            with self.subTest(count=count):
                execute = Mock(side_effect=reports)
                base = Mock(
                    return_value={
                        "package.json": "{}",
                        "package-lock.json": json.dumps(LOCK),
                    }
                )
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        run_audit(
                            {"entries": []},
                            execute,
                            Mock(),
                            mode="introduced",
                            base="base-sha",
                            read_base=base,
                        ),
                        2,
                    )
                self.assertEqual(execute.call_count, count)

    def test_introduced_mode_never_defaults_to_a_clean_baseline(self):
        for base, reader in (
            (None, Mock()),
            ("missing", Mock(side_effect=ValueError("missing commit"))),
        ):
            with self.subTest(base=base):
                execute = Mock()
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        run_audit(
                            {"entries": []},
                            execute,
                            Mock(),
                            mode="introduced",
                            base=base,
                            read_base=reader,
                        ),
                        2,
                    )
                execute.assert_not_called()

    def test_missing_current_lock_is_unavailable_not_a_security_pass(self):
        execute = Mock(return_value=result())
        with redirect_stdout(StringIO()):
            self.assertEqual(
                run_audit({"entries": []}, execute, Mock(), read_lock=lambda: None), 2
            )
        self.assertEqual(execute.call_count, 1)

    def test_malformed_baseline_lock_cannot_be_treated_as_no_previous_findings(self):
        execute = Mock(return_value=result())
        base = Mock(return_value={"package.json": "{}", "package-lock.json": "{}"})
        with redirect_stdout(StringIO()):
            self.assertEqual(
                run_audit(
                    {"entries": []},
                    execute,
                    Mock(),
                    mode="introduced",
                    base="base-sha",
                    read_base=base,
                ),
                2,
            )

    def test_trusted_runner_audits_target_lock_without_executing_target_code(self):
        target_lock = {
            "lockfileVersion": 3,
            "packages": {"": {}, "node_modules/pkg": {"version": "1.1.0"}},
        }
        target = Mock(
            return_value={
                "package.json": '{"scripts":{"postinstall":"must-not-run"}}',
                "package-lock.json": json.dumps(target_lock),
            }
        )
        visited = []

        def execute(command, **kwargs):
            self.assertEqual(command[0], "node")
            self.assertEqual(command[2], "audit")
            self.assertIn("--package-lock-only", command)
            self.assertIn("--ignore-scripts", command)
            directory = Path(command[command.index("--prefix") + 1])
            visited.append(directory)
            self.assertEqual(
                {entry.name for entry in directory.iterdir()},
                {"package.json", "package-lock.json"},
            )
            return result({"pkg": {"via": [{"source": 42, "range": "<1.1.0"}]}})

        with redirect_stdout(StringIO()):
            self.assertEqual(
                run_audit(
                    {"entries": []},
                    execute,
                    Mock(),
                    target_ref="origin/main",
                    read_base=target,
                    read_lock=Mock(side_effect=AssertionError("wrong lock")),
                ),
                0,
            )
        target.assert_called_once_with("origin/main")
        self.assertTrue(visited)
        self.assertTrue(all(not directory.exists() for directory in visited))

    def test_baseline_resolves_one_immutable_commit_before_reading_inputs(self):
        sha = "a" * 40
        execute = Mock(
            side_effect=[
                SimpleNamespace(stdout=sha + "\n"),
                SimpleNamespace(stdout='{"name":"base"}'),
                SimpleNamespace(stdout='{"lockfileVersion":3}'),
            ]
        )
        self.assertEqual(
            read_baseline("origin/dev", execute)["package.json"], '{"name":"base"}'
        )
        self.assertEqual(
            execute.call_args_list[0].args[0],
            ["git", "rev-parse", "--verify", "--end-of-options", "origin/dev^{commit}"],
        )
        self.assertEqual(
            execute.call_args_list[1].args[0], ["git", "show", f"{sha}:package.json"]
        )
        self.assertEqual(
            execute.call_args_list[2].args[0],
            ["git", "show", f"{sha}:package-lock.json"],
        )
