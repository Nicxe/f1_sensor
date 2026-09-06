"""An unavailable registry must never be interpreted as an audit result."""

from datetime import date
import unittest

from scripts.check_npm_audit import AuditUnavailable, evaluate_audit


def report(vulnerabilities=None):
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities or {},
        "metadata": {"vulnerabilities": {"total": len(vulnerabilities or {})}},
    }


class AuditTests(unittest.TestCase):
    def test_invalid_transport_responses_are_not_clean_audits(self):
        for payload in [
            None,
            {},
            [],
            {"error": {"code": "E503"}},
            {"vulnerabilities": {}},
        ]:
            with self.subTest(payload=payload), self.assertRaises(AuditUnavailable):
                evaluate_audit(payload, {"entries": []}, date(2026, 9, 4))

    def test_clean_report(self):
        self.assertEqual(
            evaluate_audit(report(), {"entries": []}, date(2026, 9, 4)), []
        )

    def test_new_finding_and_expired_exception(self):
        payload = report({"example": {"via": [{"source": 123}]}})
        self.assertIn(
            "not allowed", evaluate_audit(payload, {"entries": []}, date(2026, 9, 4))[0]
        )
        allow = {
            "entries": [
                {"package": "example", "advisory_ids": [123], "expires": "2026-09-03"}
            ]
        }
        self.assertIn("expired", evaluate_audit(payload, allow, date(2026, 9, 4))[0])

    def test_unresolvable_indirect_finding_fails_closed(self):
        with self.assertRaises(AuditUnavailable):
            evaluate_audit(
                report({"example": {"via": ["missing"]}}), {"entries": []}, date.today()
            )

    def test_stale_exception_is_only_checked_against_valid_report(self):
        allow = {
            "entries": [
                {"package": "example", "advisory_ids": [123], "expires": "2026-12-01"}
            ]
        }
        self.assertIn(
            "stale exception", evaluate_audit(report(), allow, date(2026, 9, 4))[0]
        )


if __name__ == "__main__":
    unittest.main()
