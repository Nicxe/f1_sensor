"""Runtime coverage is a line measure and excludes test helpers."""

import unittest

from scripts.check_coverage import line_coverage


class CoverageTests(unittest.TestCase):
    def test_line_threshold_does_not_use_combined_branch_percentage(self):
        report = {
            "totals": {
                "num_statements": 100,
                "covered_lines": 96,
                "percent_covered": 85,
            },
            "files": {"custom_components/f1_sensor/auth.py": {}},
        }
        self.assertEqual(line_coverage(report), 96)

    def test_empty_reports_and_test_helpers_fail_closed(self):
        for report in [
            {"totals": {"num_statements": 0}, "files": {}},
            {
                "totals": {"num_statements": 100, "covered_lines": 100},
                "files": {"custom_components/f1_sensor/tests/conftest.py": {}},
            },
        ]:
            with self.assertRaises(ValueError):
                line_coverage(report)
