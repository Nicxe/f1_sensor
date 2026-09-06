"""Retry transport failures, but never retry away a genuine policy failure."""

from contextlib import redirect_stdout
from io import StringIO
import json
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts.run_npm_audit import run_audit


class RunnerTests(unittest.TestCase):
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
            payload = {
                "auditReportVersion": 2,
                "vulnerabilities": vulnerabilities,
                "metadata": {"vulnerabilities": {"total": len(vulnerabilities)}},
            }
            run = Mock(
                return_value=SimpleNamespace(
                    returncode=status, stdout=json.dumps(payload)
                )
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(run_audit({"entries": []}, run, Mock()), status)
            self.assertEqual(run.call_count, 1)
