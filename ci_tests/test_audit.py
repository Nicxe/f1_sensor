"""An unavailable registry must never be interpreted as an audit result."""

from datetime import date
import json
from pathlib import Path
import unittest

from scripts.check_npm_audit import AuditUnavailable, evaluate_audit


def report(vulnerabilities=None):
    vulnerabilities = {
        name: {"severity": "high", "nodes": [f"node_modules/{name}"], **details}
        for name, details in (vulnerabilities or {}).items()
    }
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

    def test_stale_exception_does_not_block_a_fixed_dependency(self):
        allow = {
            "entries": [
                {"package": "example", "advisory_ids": [123], "expires": "2026-12-01"}
            ]
        }
        self.assertEqual(evaluate_audit(report(), allow, date(2026, 9, 4)), [])

    def test_bundled_exception_does_not_allow_other_dependency_paths(self):
        bundled = "node_modules/npm/node_modules/example"
        allow = {
            "entries": [
                {
                    "package": "example",
                    "advisory_ids": [123],
                    "allowed_nodes": [bundled],
                    "expires": "2026-10-31",
                }
            ]
        }
        for nodes in ([bundled], [bundled, "node_modules/example"], [], None):
            with self.subTest(nodes=nodes):
                payload = report(
                    {"example": {"via": [{"source": 123}], "nodes": nodes}}
                )
                if not nodes:
                    with self.assertRaises(AuditUnavailable):
                        evaluate_audit(payload, allow, date(2026, 10, 1))
                    continue
                failures = evaluate_audit(payload, allow, date(2026, 10, 1))
                if nodes == [bundled]:
                    self.assertEqual(failures, [])
                else:
                    self.assertIn("outside allowed nodes", failures[0])

    def test_approved_undici_exception_is_scoped_and_expires(self):
        allow = json.loads(
            (
                Path(__file__).resolve().parents[1] / "quality/npm-audit-allowlist.json"
            ).read_text(encoding="utf-8")
        )
        exception = next(
            item for item in allow["entries"] if item["package"] == "undici"
        )
        bundled = "node_modules/npm/node_modules/undici"
        self.assertEqual(exception["advisory_ids"], [1243114])
        self.assertEqual(exception["allowed_nodes"], [bundled])
        self.assertEqual(exception["expires"], "2026-10-31")

        payload = report({"undici": {"via": [{"source": 1243114}], "nodes": [bundled]}})
        self.assertEqual(evaluate_audit(payload, allow, date(2026, 10, 31)), [])
        self.assertIn(
            "expired exception", evaluate_audit(payload, allow, date(2026, 11, 1))[0]
        )

        payload["vulnerabilities"]["undici"]["nodes"].append("node_modules/undici")
        self.assertIn(
            "outside allowed nodes",
            evaluate_audit(payload, allow, date(2026, 10, 24))[0],
        )
        payload["vulnerabilities"]["undici"]["nodes"] = [bundled]
        payload["vulnerabilities"]["undici"]["via"] = [{"source": 1243115}]
        self.assertIn(
            "1243115 is not allowed",
            evaluate_audit(payload, allow, date(2026, 10, 24))[0],
        )

    def test_invalid_node_scope_fails_closed(self):
        for nodes in ([], "node_modules/example", [None]):
            with self.subTest(nodes=nodes):
                allow = {
                    "entries": [
                        {
                            "package": "example",
                            "advisory_ids": [123],
                            "allowed_nodes": nodes,
                            "expires": "2026-10-31",
                        }
                    ]
                }
                self.assertIn(
                    "invalid allowed nodes",
                    evaluate_audit(report(), allow, date(2026, 10, 1))[0],
                )

    def test_expired_unused_exception_warns_without_blocking_fixed_dependency(self):
        allow = {
            "entries": [
                {"package": "fixed", "advisory_ids": [123], "expires": "2026-09-01"}
            ]
        }
        warnings = []
        self.assertEqual(
            evaluate_audit(report(), allow, date(2026, 10, 20), warnings=warnings), []
        )
        self.assertIn("unused expired exception", warnings[0])

    def test_only_matching_active_advisory_can_be_blocked_by_expiry(self):
        allow = {
            "entries": [
                {"package": "example", "advisory_ids": [123], "expires": "2026-09-01"}
            ]
        }
        payload = report({"example": {"via": [{"source": 456}]}})
        failures = evaluate_audit(payload, allow, date(2026, 10, 20))
        self.assertEqual(len(failures), 1)
        self.assertIn("456 is not allowed", failures[0])

    def test_expiring_active_exception_warns_before_it_can_block(self):
        allow = {
            "entries": [
                {"package": "example", "advisory_ids": [123], "expires": "2026-10-31"}
            ]
        }
        warnings = []
        payload = report({"example": {"via": [{"source": 123}]}})
        self.assertEqual(
            evaluate_audit(payload, allow, date(2026, 10, 20), warnings=warnings), []
        )
        self.assertTrue(any("in 11 day(s)" in warning for warning in warnings))

    def test_severity_policy_never_excludes_development_tooling(self):
        for severity in ("low", "moderate", "high", "critical"):
            with self.subTest(severity=severity):
                warnings = []
                payload = report(
                    {
                        "tool": {
                            "via": [{"source": 123}],
                            "severity": severity,
                            "isDev": True,
                        }
                    }
                )
                failures = evaluate_audit(
                    payload, {"entries": []}, date.today(), warnings=warnings
                )
                self.assertEqual(bool(failures), severity in ("high", "critical"))
                if not failures:
                    self.assertTrue(warnings)

    def test_introduced_mode_preserves_existing_findings_but_blocks_new_paths(self):
        old = report({"example": {"via": [{"source": 123}]}})
        warnings = []
        self.assertEqual(
            evaluate_audit(
                old, {"entries": []}, date.today(), baseline=old, warnings=warnings
            ),
            [],
        )
        self.assertIn("no new vulnerable dependency path", warnings[0])
        current = report(
            {
                "example": {
                    "via": [{"source": 123}],
                    "nodes": [
                        "node_modules/example",
                        "node_modules/other/node_modules/example",
                    ],
                }
            }
        )
        failures = evaluate_audit(current, {"entries": []}, date.today(), baseline=old)
        self.assertEqual(len(failures), 1)
        self.assertIn("node_modules/other/node_modules/example", failures[0])

    def test_new_advisory_at_existing_path_is_introduced(self):
        old = report({"example": {"via": [{"source": 123}]}})
        current = report({"example": {"via": [{"source": 456}]}})
        self.assertIn(
            "456 is not allowed",
            evaluate_audit(current, {"entries": []}, date.today(), baseline=old)[0],
        )

    def test_new_blocking_severity_at_an_existing_path_is_not_ignored(self):
        old = report({"example": {"severity": "moderate", "via": [{"source": 123}]}})
        current = report({"example": {"via": [{"source": 123}]}})
        self.assertTrue(
            evaluate_audit(current, {"entries": []}, date.today(), baseline=old)
        )

    def test_duplicate_advisory_never_downgrades_the_strongest_severity(self):
        current = report(
            {
                "example": {
                    "via": [
                        {"source": 123, "severity": "critical"},
                        {"source": 123, "severity": "low"},
                    ]
                }
            }
        )
        self.assertTrue(evaluate_audit(current, {"entries": []}, date.today()))

    def test_indirect_cycle_cannot_hide_behind_another_resolved_advisory(self):
        payload = report(
            {
                "first": {"via": ["second"]},
                "second": {"via": ["first"]},
                "resolved": {"via": [{"source": 123}]},
            }
        )
        with self.assertRaises(AuditUnavailable):
            evaluate_audit(payload, {"entries": []}, date.today())

    def test_exception_scope_applies_to_introduced_path_not_an_accepted_old_path(self):
        old = report({"example": {"via": [{"source": 123}]}})
        current = report(
            {
                "example": {
                    "via": [{"source": 123}],
                    "nodes": [
                        "node_modules/example",
                        "node_modules/other/node_modules/example",
                    ],
                }
            }
        )
        allow = {
            "entries": [
                {
                    "package": "example",
                    "advisory_ids": [123],
                    "allowed_nodes": ["node_modules/example"],
                    "expires": "2026-10-31",
                }
            ]
        }
        self.assertIn(
            "outside allowed nodes",
            evaluate_audit(current, allow, date(2026, 10, 20), baseline=old)[0],
        )

    def test_invalid_baseline_or_missing_severity_is_not_a_security_pass(self):
        with self.assertRaises(AuditUnavailable):
            evaluate_audit(report(), {"entries": []}, date.today(), baseline={})
        payload = report({"example": {"via": [{"source": 123}]}})
        del payload["vulnerabilities"]["example"]["severity"]
        with self.assertRaises(AuditUnavailable):
            evaluate_audit(payload, {"entries": []}, date.today())


if __name__ == "__main__":
    unittest.main()
