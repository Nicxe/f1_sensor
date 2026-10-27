"""An unavailable registry must never be interpreted as an audit result."""

from datetime import date
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.check_npm_audit import (
    AuditUnavailable,
    audit_findings,
    evaluate_audit as evaluate_with_versions,
    match_advisory_versions,
    project_npm_cli,
)


def report(vulnerabilities=None):
    vulnerabilities = {
        name: {"severity": "high", "nodes": [f"node_modules/{name}"], **details}
        for name, details in (vulnerabilities or {}).items()
    }
    for details in vulnerabilities.values():
        if isinstance(details.get("via"), list):
            details["via"] = [
                {"range": "*", **item} if isinstance(item, dict) else item
                for item in details["via"]
            ]
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities or {},
        "metadata": {"vulnerabilities": {"total": len(vulnerabilities or {})}},
    }


def locked(payload, versions=None):
    """Explicit package-lock fixture; policy tests use a uniform safe version."""
    versions = {} if versions is None else versions
    return {
        "lockfileVersion": 3,
        "packages": {
            "": {},
            **{
                node: {"version": versions.get(node, "1.0.0")}
                for entry in payload.get("vulnerabilities", {}).values()
                for node in (entry.get("nodes") or [])
            },
        },
    }


def evaluate_audit(payload, allowlist, today, **kwargs):
    """Isolate policy behavior from semver, which is exercised separately below."""
    kwargs.setdefault("lock", locked(payload) if isinstance(payload, dict) else None)
    if isinstance(kwargs.get("baseline"), dict):
        kwargs.setdefault("baseline_lock", locked(kwargs["baseline"]))

    def match_all_versions(records):
        if any(record["range"] != "*" for record in records):
            raise AssertionError("policy fixture must use an explicit match-all range")
        return [True] * len(records)

    return evaluate_with_versions(
        payload, allowlist, today, match_versions=match_all_versions, **kwargs
    )


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
        bundled = "node_modules/npm/node_modules/undici"
        # Historical approval is fixed fixture data, not a requirement for this
        # exception to remain in the live list after npm repairs its bundle.
        allow = {
            "entries": [
                {
                    "package": "undici",
                    "advisory_ids": [1243114],
                    "allowed_nodes": [bundled],
                    "expires": "2026-10-31",
                }
            ]
        }

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
        payload["vulnerabilities"]["undici"]["via"] = [
            {"source": 1243115, "range": "*"}
        ]
        self.assertIn(
            "1243115 is not allowed",
            evaluate_audit(payload, allow, date(2026, 10, 24))[0],
        )

    def test_live_exceptions_remain_explained_narrow_and_removable(self):
        allow = json.loads(
            (
                Path(__file__).resolve().parents[1] / "quality/npm-audit-allowlist.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIsInstance(allow.get("entries"), list)
        for entry in allow["entries"]:
            with self.subTest(package=entry.get("package")):
                self.assertTrue(entry.get("reason", "").strip())
                self.assertTrue(entry.get("scope", "").strip())
                self.assertIsInstance(date.fromisoformat(entry["expires"]), date)
                self.assertTrue(entry.get("allowed_nodes"))
                self.assertTrue(all("*" not in node for node in entry["allowed_nodes"]))
        # Expired unused approvals and removing all repaired approvals must not
        # prevent a clean dependency graph from passing.
        self.assertEqual(evaluate_audit(report(), allow, date(2100, 1, 1)), [])
        self.assertEqual(
            evaluate_audit(report(), {"entries": []}, date(2100, 1, 1)), []
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


class NpmCliResolutionTests(unittest.TestCase):
    @staticmethod
    def cli(directory, version):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "package.json").write_text(
            json.dumps({"name": "npm", "version": version})
        )
        binary = directory / "bin/npm-cli.js"
        binary.parent.mkdir()
        binary.write_text("// Resolver fixture; never executed.\n")
        (binary.parent / "npm").symlink_to(binary)
        return binary.resolve()

    def test_inherited_wrong_global_and_shadowed_release_npm_use_private_pin(self):
        with tempfile.TemporaryDirectory(prefix="f1-npm-resolve-") as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"packageManager":"npm@10.9.8"}')
            private = self.cli(root / ".tools-ci/node_modules/npm", "10.9.8")
            global_cli = self.cli(root / "global/npm", "11.0.0")
            release_cli = self.cli(root / "node_modules/npm", "12.2.1")
            environment = {
                "npm_execpath": str(global_cli),
                "PATH": str(release_cli.parent),
            }
            self.assertEqual(
                project_npm_cli(root=root, environment=environment), private
            )

    def test_valid_inherited_pin_takes_precedence_over_private_fallback(self):
        with tempfile.TemporaryDirectory(prefix="f1-npm-resolve-") as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"packageManager":"npm@10.9.8"}')
            self.cli(root / ".tools-ci/node_modules/npm", "10.9.8")
            inherited = self.cli(root / "inherited/npm", "10.9.8")
            self.assertEqual(
                project_npm_cli(
                    root=root, environment={"npm_execpath": str(inherited), "PATH": ""}
                ),
                inherited,
            )

    def test_standalone_audit_finds_exact_pin_on_path_without_project_install(self):
        with tempfile.TemporaryDirectory(prefix="f1-npm-resolve-") as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"packageManager":"npm@10.9.8"}')
            wrong = self.cli(root / "global/npm", "11.0.0")
            pinned = self.cli(root / "pinned/npm", "10.9.8")
            environment = {
                "npm_execpath": str(wrong),
                "PATH": os.pathsep.join((str(wrong.parent), str(pinned.parent))),
            }
            self.assertEqual(
                project_npm_cli(root=root, environment=environment), pinned
            )
            self.assertFalse((root / "node_modules").exists())

    def test_no_matching_pin_is_unavailable_not_an_unpinned_fallback(self):
        with tempfile.TemporaryDirectory(prefix="f1-npm-resolve-") as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"packageManager":"npm@10.9.8"}')
            wrong = self.cli(root / "global/npm", "12.2.1")
            with self.assertRaises(AuditUnavailable):
                project_npm_cli(
                    root=root,
                    environment={"npm_execpath": str(wrong), "PATH": str(wrong.parent)},
                )


class AdvisoryVersionTests(unittest.TestCase):
    def test_bridge_uses_pinned_npms_semver_without_a_project_install(self):
        root = Path(__file__).resolve().parents[1]
        version = json.loads((root / "package.json").read_text())["packageManager"][4:]
        with tempfile.TemporaryDirectory(prefix="f1-semver-test-") as directory:
            for requested, status in ((version, 0), ("0.0.0", 2)):
                result = subprocess.run(
                    [
                        "node",
                        str(root / "scripts/npm_audit_semver.cjs"),
                        str(project_npm_cli()),
                        requested,
                    ],
                    input='[{"version":"6.29.0","range":"<6.29.1"}]',
                    text=True,
                    capture_output=True,
                    cwd=directory,
                    check=False,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                if status == 0:
                    self.assertEqual(json.loads(result.stdout), [True])

    def test_official_semver_handles_npm_ranges_and_prereleases(self):
        self.assertEqual(
            match_advisory_versions(
                [
                    {"version": "1.2.4", "range": "1.2.3 - 2.0.0"},
                    {"version": "1.2.4", "range": "^1.2.3 || ~3.4"},
                    {"version": "3.4.9", "range": "^1.2.3 || ~3.4"},
                    {"version": "2.0.0", "range": ">=1 <2"},
                    {"version": "1.3.0-beta.1", "range": "^1.2.0"},
                    {"version": "1.3.0-beta.1", "range": ">=1.3.0-beta.0 <1.3.0"},
                    {"version": "1.9.1", "range": "1.x"},
                ]
            ),
            [True, True, True, False, True, True, True],
        )

    def test_advisories_only_receive_their_own_vulnerable_versions_and_paths(self):
        bundled = "node_modules/npm/node_modules/undici"
        ordinary = "node_modules/undici"
        payload = report(
            {
                "undici": {
                    "nodes": [bundled, ordinary],
                    "via": [
                        {"source": 123, "range": ">=6.23.0 <6.29.1"},
                        {"source": 456, "range": ">=7.18.0 <7.30.1"},
                    ],
                }
            }
        )
        findings = audit_findings(
            payload, locked(payload, {bundled: "6.29.0", ordinary: "7.30.1"})
        )
        self.assertEqual(set(findings), {("undici", 123)})
        self.assertEqual(findings[("undici", 123)]["nodes"], {bundled})
        findings = audit_findings(
            payload, locked(payload, {bundled: "6.29.0", ordinary: "7.30.0"})
        )
        self.assertEqual(findings[("undici", 456)]["nodes"], {ordinary})
        allow = {
            "entries": [
                {
                    "package": "undici",
                    "advisory_ids": [123],
                    "allowed_nodes": [bundled],
                    "expires": "2026-10-31",
                }
            ]
        }
        self.assertEqual(
            evaluate_with_versions(
                payload,
                allow,
                date(2026, 10, 24),
                lock=locked(payload, {bundled: "6.29.0", ordinary: "7.30.1"}),
            ),
            [],
        )

    def test_introduced_mode_uses_each_commits_locked_version(self):
        payload = report({"undici": {"via": [{"source": 123, "range": "<6.29.1"}]}})
        vulnerable = locked(payload, {"node_modules/undici": "6.29.0"})
        fixed = locked(payload, {"node_modules/undici": "6.29.1"})
        self.assertTrue(
            evaluate_with_versions(
                payload,
                {"entries": []},
                date.today(),
                lock=vulnerable,
                baseline=payload,
                baseline_lock=fixed,
            )
        )
        self.assertEqual(
            evaluate_with_versions(
                payload,
                {"entries": []},
                date.today(),
                lock=fixed,
                baseline=payload,
                baseline_lock=vulnerable,
            ),
            [],
        )

    def test_missing_malformed_or_mismatched_version_evidence_fails_closed(self):
        payload = report({"example": {"via": [{"source": 123}]}})
        for lock in (
            None,
            {},
            {"lockfileVersion": 3, "packages": {}},
            {"lockfileVersion": 3, "packages": {"": {}}},
            locked(payload, {"node_modules/example": "not-semver"}),
        ):
            with self.subTest(lock=lock), self.assertRaises(AuditUnavailable):
                audit_findings(payload, lock)
        for advisory_range in (None, "", "not a range"):
            current = report(
                {"example": {"via": [{"source": 123, "range": advisory_range}]}}
            )
            with (
                self.subTest(range=advisory_range),
                self.assertRaises(AuditUnavailable),
            ):
                audit_findings(current, locked(current))

    def test_absent_lock_evidence_is_not_clean_even_with_empty_registry_report(self):
        with self.assertRaises(AuditUnavailable):
            audit_findings(report(), None)

    def test_nodes_cannot_borrow_another_package_version_or_escape_lock_scope(self):
        for node in (
            "node_modules/different",
            "../node_modules/example",
            "not_node_modules/example",
            "node_modules/example/../example",
        ):
            payload = report({"example": {"nodes": [node], "via": [{"source": 123}]}})
            with self.subTest(node=node), self.assertRaises(AuditUnavailable):
                audit_findings(payload, locked(payload))

    def test_scoped_and_nested_packages_keep_their_exact_path(self):
        node = "node_modules/@scope/parent/node_modules/@scope/example"
        payload = report(
            {"@scope/example": {"nodes": [node], "via": [{"source": 123}]}}
        )
        findings = audit_findings(payload, locked(payload))
        self.assertEqual(findings[("@scope/example", 123)]["nodes"], {node})

    def test_invalid_metavulnerability_lock_version_is_not_ignored(self):
        payload = report(
            {"parent": {"via": ["example"]}, "example": {"via": [{"source": 123}]}}
        )
        with self.assertRaises(AuditUnavailable):
            audit_findings(payload, locked(payload, {"node_modules/parent": "broken"}))


if __name__ == "__main__":
    unittest.main()
