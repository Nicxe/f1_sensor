"""Runtime coverage is a line measure and excludes test helpers."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.check_coverage import line_coverage


def coverage_report(*modules):
    files = {
        f"custom_components/f1_sensor/{name}.py": {
            "summary": {"num_statements": statements, "covered_lines": covered}
        }
        for name, statements, covered in modules
    }
    return {
        "totals": {
            "num_statements": sum(item[1] for item in modules),
            "covered_lines": sum(item[2] for item in modules),
            "percent_covered": 85,
        },
        "files": files,
    }


class CoverageTests(unittest.TestCase):
    def test_line_threshold_does_not_use_combined_branch_percentage(self):
        report = coverage_report(("auth", 100, 96))
        self.assertEqual(line_coverage(report), 96)

    def run_checker(self, report):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_text(json.dumps(report))
            return subprocess.run(
                [sys.executable, "scripts/check_coverage.py", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_module_below_floor_cannot_hide_behind_high_total(self):
        result = self.run_checker(
            coverage_report(("auth", 100, 94), ("signalr", 1000, 1000))
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auth.py", result.stdout)

    def test_exactly_95_percent_is_not_above_the_floor(self):
        for report in (
            coverage_report(("auth", 100, 95)),
            coverage_report(("auth", 100, 95), ("signalr", 1000, 1000)),
            coverage_report(("auth", 100000, 94999)),
        ):
            with self.subTest(report=report):
                self.assertNotEqual(self.run_checker(report).returncode, 0)

    def test_strictly_above_floor_and_empty_module_pass(self):
        result = self.run_checker(
            coverage_report(("auth", 10000, 9501), ("__init__", 0, 0))
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_inconsistent_and_invalid_report_counts_fail_closed(self):
        reports = [
            {},
            coverage_report(),
            coverage_report(("auth", 100, 101)),
            coverage_report(("auth", -1, -1)),
            coverage_report(("auth", 100.0, 100.0)),
            coverage_report(("auth", True, True)),
        ]
        inconsistent = coverage_report(("auth", 100, 94))
        inconsistent["totals"]["covered_lines"] = 100
        reports.append(inconsistent)
        missing_files = coverage_report(("auth", 100, 100))
        missing_files["files"] = {}
        reports.append(missing_files)
        missing_summary = coverage_report(("auth", 100, 100))
        missing_summary["files"]["custom_components/f1_sensor/auth.py"] = {}
        reports.append(missing_summary)
        for report in reports:
            with self.subTest(report=report):
                self.assertNotEqual(self.run_checker(report).returncode, 0)

    def test_empty_reports_and_test_helpers_fail_closed(self):
        for report in [
            {"totals": {"num_statements": 0}, "files": {}},
            coverage_report(("tests/conftest", 100, 100)),
            coverage_report(("tests\\conftest", 100, 100)),
        ]:
            with self.assertRaises(ValueError):
                line_coverage(report)
