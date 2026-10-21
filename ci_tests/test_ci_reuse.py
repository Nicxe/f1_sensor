"""Reuse requires authoritative evidence for the same complete Git tree."""

from datetime import UTC, datetime, timedelta
import unittest

from scripts.ci_reuse import (
    REUSABLE,
    eligible_run,
    evidence_checks,
    find_evidence,
    reuse_allowed,
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

    def test_only_recent_successful_exact_tree_verifications(self):
        self.assertTrue(eligible_run(self.run, self.now))
        self.assertFalse(
            eligible_run(
                self.run
                | {
                    "event": "pull_request",
                    "path": ".github/workflows/ci.yml",
                    "head_branch": "feature",
                },
                self.now,
            )
        )
        for changes in [
            {"event": "pull_request", "path": "other.yml"},
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

    def test_backend_requires_the_current_profile(self):
        jobs = [{"name": name, "conclusion": "success"} for name in REUSABLE["backend"]]
        self.assertIn("backend", successful_checks(jobs))
        for result in ["failure", "cancelled", "skipped", None]:
            jobs[0]["conclusion"] = result
            self.assertNotIn("backend", successful_checks(jobs))

    def test_validation_is_reused_but_audit_is_always_fresh(self):
        self.assertIn("validation", REUSABLE)
        self.assertNotIn("audit", REUSABLE)

    def test_only_prs_can_reuse_and_every_push_runs_fresh(self):
        self.assertTrue(reuse_allowed("pull_request", "beta", True))
        self.assertFalse(reuse_allowed("push", "beta", True))
        self.assertFalse(reuse_allowed("push", "main", True))
        self.assertFalse(reuse_allowed("push", "dev", True))
        self.assertFalse(reuse_allowed("workflow_dispatch", "main", True))
        self.assertFalse(reuse_allowed("push", "main", False))


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
            "tree_sha": self.tree,
            "checks": ["backend"],
        }

    def test_equal_tree_and_verified_profiles_can_be_reused(self):
        self.assertEqual(
            evidence_checks(self.api, self.run, "tree", self.now), {"backend"}
        )
        verify_evidence(self.api, self.evidence, "tree", self.now)

    def test_pr_head_never_proves_which_merge_tree_was_tested(self):
        pr_run = self.run | {
            "event": "pull_request",
            "path": ".github/workflows/ci.yml",
            "head_branch": "dev",
        }

        class API:
            def get(self, path):
                if path.startswith("actions/workflows/development.yml"):
                    return {"workflow_runs": []}
                raise AssertionError(f"PR evidence must not be queried: {path}")

        self.assertEqual(
            find_evidence(API(), {"backend": True}, self.tree, self.now),
            {},
        )
        self.assertEqual(evidence_checks(self.api, pr_run, self.tree, self.now), set())

    def test_evidence_records_the_exact_push_tree(self):
        outer = self

        class API:
            def get(self, path):
                if path.startswith("actions/workflows/development.yml"):
                    return {"workflow_runs": [outer.run]}
                return outer.api.get(path)

            def jobs(self, run_id):
                return outer.api.jobs(run_id)

        self.assertEqual(
            find_evidence(API(), {"backend": True}, self.tree, self.now),
            self.evidence,
        )

    def test_unbound_tree_evidence_is_rejected(self):
        for recorded_tree in (None, "another-tree"):
            with self.subTest(tree=recorded_tree), self.assertRaises(ValueError):
                verify_evidence(
                    self.api,
                    self.evidence | {"tree_sha": recorded_tree},
                    self.tree,
                    self.now,
                )

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
        for check in ["audit", "unknown"]:
            with self.subTest(check=check), self.assertRaises(ValueError):
                verify_evidence(
                    self.api, self.evidence | {"checks": [check]}, "tree", self.now
                )
