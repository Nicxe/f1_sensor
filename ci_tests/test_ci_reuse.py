"""Reuse requires authoritative evidence for the same complete Git tree."""

from datetime import UTC, datetime, timedelta
import unittest

from scripts.ci_reuse import (
    REUSABLE,
    eligible_run,
    evidence_checks,
    successful_checks,
    verify_evidence,
)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(UTC)
        self.run = {
            "event": "push",
            "path": ".github/workflows/development.yml",
            "head_branch": "dev",
            "head_sha": "a" * 40,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
            "updated_at": self.now.isoformat(),
        }

    def test_only_recent_successful_trusted_development_pushes(self):
        self.assertTrue(eligible_run(self.run, self.now))
        for changes in [
            {"event": "pull_request"},
            {"head_branch": "feature"},
            {"conclusion": "failure"},
            {"conclusion": "cancelled"},
            {"status": "in_progress"},
            {"path": "other.yml"},
            {"updated_at": (self.now - timedelta(hours=3)).isoformat()},
            {"updated_at": "invalid"},
            {"head_sha": ""},
        ]:
            with self.subTest(changes=changes):
                self.assertFalse(eligible_run(self.run | changes, self.now))

    def test_matrix_requires_every_profile_and_no_missing_jobs(self):
        jobs = [{"name": name, "conclusion": "success"} for name in REUSABLE["backend"]]
        self.assertIn("backend", successful_checks(jobs))
        self.assertNotIn("backend", successful_checks(jobs[:1]))
        for result in ["failure", "cancelled", "skipped", None]:
            jobs[1]["conclusion"] = result
            self.assertNotIn("backend", successful_checks(jobs))

    def test_remote_validation_and_audit_are_never_reused(self):
        self.assertNotIn("audit", REUSABLE)
        self.assertNotIn("validation", REUSABLE)


class EvidenceTests(ReuseTests):
    def setUp(self):
        super().setUp()
        self.run.update(id=42)
        self.tree = "tree"
        outer = self

        class API:
            def get(self, path):
                return (
                    {"tree": {"sha": outer.tree}}
                    if path.startswith("git/")
                    else outer.run
                )

            def jobs(self, run_id):
                return outer.jobs

        self.api = API()
        self.jobs = [
            {"name": "checks / Verify selected checks", "conclusion": "success"}
        ]
        self.jobs += [
            {"name": name, "conclusion": "success"} for name in REUSABLE["backend"]
        ]
        self.evidence = {
            "run_id": 42,
            "attempt": 1,
            "head_sha": "a" * 40,
            "checks": ["backend"],
        }

    def test_equal_tree_and_verified_profiles_can_be_reused(self):
        self.assertEqual(
            evidence_checks(self.api, self.run, "tree", self.now), {"backend"}
        )
        verify_evidence(self.api, self.evidence, "tree", self.now)

    def test_changed_sources_workflow_or_dependencies_force_fresh_checks(self):
        self.assertEqual(
            evidence_checks(self.api, self.run, "different-tree", self.now), set()
        )
        with self.assertRaises(ValueError):
            verify_evidence(self.api, self.evidence, "different-tree", self.now)

    def test_missing_gate_or_restarted_source_invalidates_evidence(self):
        self.jobs.pop(0)
        self.assertEqual(evidence_checks(self.api, self.run, "tree", self.now), set())
        self.run["run_attempt"] = 2
        with self.assertRaises(ValueError):
            verify_evidence(self.api, self.evidence, "tree", self.now)

    def test_unknown_or_remote_checks_cannot_be_claimed(self):
        for check in ["audit", "validation", "unknown"]:
            with self.subTest(check=check), self.assertRaises(ValueError):
                verify_evidence(
                    self.api, self.evidence | {"checks": [check]}, "tree", self.now
                )
