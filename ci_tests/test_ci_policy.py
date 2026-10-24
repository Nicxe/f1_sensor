"""Acceptance cases for required checks and branch routing."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.ci_policy import (
    JOBS,
    audit_context,
    branch_error,
    gate_errors,
    hotfix_matches_dev,
    main,
    main_promotion_release_error,
    release_product_checks,
    release_triggering_commits,
    select_jobs,
    should_deploy,
)


def pull(base, head, fork=False):
    return {
        "pull_request": {
            "base": {
                "ref": base,
                "sha": "a" * 40,
                "repo": {"full_name": "Nicxe/f1_sensor"},
            },
            "head": {
                "ref": head,
                "sha": "b" * 40,
                "repo": {"full_name": "fork/repo" if fork else "Nicxe/f1_sensor"},
            },
            "user": {"login": "contributor"},
        }
    }


class PolicyTests(unittest.TestCase):
    def test_owner_hotfix_is_routing_exempt_and_contributors_are_guided(self):
        event = pull("beta", "hotfix/issue-799-multipart-session")
        event["pull_request"]["user"]["login"] = "Nicxe"
        files = ["custom_components/f1_sensor/live_window.py"]
        with patch("scripts.ci_policy.hotfix_matches_dev") as check:
            self.assertEqual(branch_error(event, files), "")
            check.assert_not_called()
        event["pull_request"]["user"]["login"] = "contributor"
        self.assertTrue(branch_error(event, files))
        event["pull_request"]["head"]["repo"]["full_name"] = "fork/repo"
        self.assertTrue(branch_error(event, files))

    def test_hotfix_check_requires_every_patch_on_dev(self):
        base_sha, head_sha = "a" * 40, "b" * 40
        self.assertFalse(hotfix_matches_dev([], base_sha=base_sha, head_sha=head_sha))
        self.assertFalse(
            hotfix_matches_dev(["file.py"], base_sha="bad", head_sha=head_sha)
        )
        with patch("scripts.ci_policy.subprocess.run") as run:
            run.side_effect = [
                Mock(returncode=0, stdout=f"{head_sha}\n"),
                Mock(returncode=0, stdout=f"- {head_sha}\n"),
            ]
            self.assertTrue(
                hotfix_matches_dev(["file.py"], base_sha=base_sha, head_sha=head_sha)
            )
            self.assertEqual(run.call_count, 2)
        with patch("scripts.ci_policy.subprocess.run") as run:
            run.side_effect = [
                Mock(returncode=0, stdout=f"{head_sha}\n"),
                Mock(returncode=0, stdout=f"+ {head_sha}\n"),
            ]
            self.assertFalse(
                hotfix_matches_dev(["file.py"], base_sha=base_sha, head_sha=head_sha)
            )

        with patch("scripts.ci_policy.subprocess.run") as run:
            run.side_effect = [
                Mock(returncode=0, stdout=f"{head_sha}\n{'c' * 40}\n"),
                Mock(returncode=0, stdout=f"- {head_sha}\n"),
            ]
            self.assertFalse(
                hotfix_matches_dev(["file.py"], base_sha=base_sha, head_sha=head_sha)
            )
        with patch("scripts.ci_policy.subprocess.run") as run:
            run.return_value = Mock(returncode=1)
            self.assertFalse(
                hotfix_matches_dev(["file.py"], base_sha=base_sha, head_sha=head_sha)
            )

    def test_main_promotion_rejects_release_commits_already_on_main(self):
        event = pull("main", "beta")
        with (
            patch("scripts.ci_policy.latest_stable_release_tag", return_value="v5.7.3"),
            patch(
                "scripts.ci_policy.release_triggering_commits",
                return_value=[
                    ("a" * 40, "feat(card): Add an unintended stable feature"),
                    ("b" * 40, "fix: Correct an unintended stable behavior"),
                ],
            ),
        ):
            error = main_promotion_release_error(event)
        self.assertIn("2 unreleased feat/fix", error)
        self.assertIn("v5.7.3", error)
        self.assertIn("aaaaaaa", error)

    def test_main_promotion_accepts_a_clean_release_boundary(self):
        event = pull("main", "beta")
        with (
            patch("scripts.ci_policy.latest_stable_release_tag", return_value="v5.7.3"),
            patch("scripts.ci_policy.release_triggering_commits", return_value=[]),
        ):
            self.assertEqual(main_promotion_release_error(event), "")
        self.assertEqual(main_promotion_release_error(pull("beta", "dev")), "")

    def test_release_boundary_uses_semantic_release_exclusions(self):
        output = "\n".join(
            [
                f"{'a' * 40}\x00fix(compatibility): Verify release tags from GitHub directly",
                f"{'b' * 40}\x00fix(compatibility): tolerate delayed release assets",
                f"{'c' * 40}\x00fix(ci): wait for promotion verification registration",
                f"{'d' * 40}\x00fix: Correct an unintended stable behavior",
            ]
        )
        with patch(
            "scripts.ci_policy.subprocess.run",
            return_value=Mock(returncode=0, stdout=output),
        ):
            self.assertEqual(
                release_triggering_commits("v6.0.0..main"),
                [("d" * 40, "fix: Correct an unintended stable behavior")],
            )

    def test_owner_prs_can_target_maintenance_branches_without_routing_warnings(self):
        event = pull("main", "maintenance/dependency-ci-recovery")
        event["pull_request"]["user"]["login"] = "Nicxe"
        files = [
            "package.json",
            "CONTRIBUTING.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/scripts/auto-merge.cjs",
            "scripts/ci_policy.py",
            "scripts/check_npm_audit.py",
            "scripts/run_npm_audit.py",
            "ci_tests/test_ci_policy.py",
        ]
        self.assertEqual(branch_error(event, files), "")
        for base, head, changed in [
            ("main", "maintenance/workflows", [".github/workflows/ci.yml"]),
            ("dev", "feature/work", ["custom_components/f1_sensor/sensor.py"]),
            ("content", "maintenance/docs", ["docs/help.md"]),
            ("beta", "hotfix/urgent", ["scripts/other.py"]),
        ]:
            with self.subTest(base=base, head=head):
                owner_event = pull(base, head)
                owner_event["pull_request"]["user"]["login"] = "Nicxe"
                self.assertEqual(branch_error(owner_event, changed), "")
        event["pull_request"]["user"]["login"] = "contributor"
        self.assertTrue(branch_error(event, files))
        event["pull_request"]["user"]["login"] = "Nicxe"
        event["pull_request"]["head"]["repo"]["full_name"] = "fork/repo"
        self.assertTrue(branch_error(event, files))

    def test_dependabot_default_branch_dependency_exception_is_narrow(self):
        event = pull("main", "dependabot/pip/requirements/pycares-4.9.0")
        event["pull_request"]["user"]["login"] = "dependabot[bot]"
        files = ["requirements/ha-minimum.txt"]
        self.assertEqual(branch_error(event, files), "")
        self.assertTrue(
            all(
                enabled
                for job, enabled in select_jobs(
                    files, event, "pull_request", ""
                ).items()
                if job not in ("blueprints", "audit")
            )
        )
        for changed in [
            [],
            ["scripts/ci_policy.py"],
            ["custom_components/f1_sensor/sensor.py"],
        ]:
            self.assertTrue(branch_error(event, changed))
        event["pull_request"]["user"]["login"] = "contributor"
        self.assertTrue(branch_error(event, files))
        event["pull_request"]["user"]["login"] = "dependabot[bot]"
        event["pull_request"]["head"]["repo"]["full_name"] = "fork/repo"
        self.assertTrue(branch_error(event, files))

    def test_site_deploy_depends_on_content_even_when_release_tests_run(self):
        self.assertFalse(
            should_deploy(["custom_components/f1_sensor/auth.py"], "push", "main")
        )
        self.assertTrue(should_deploy(["docs/help.md"], "push", "main"))
        self.assertTrue(should_deploy(["docs/help.md"], "push", "beta"))
        self.assertFalse(should_deploy(["docs/help.md"], "pull_request", "main"))
        self.assertTrue(should_deploy(None, "push", "beta"))
        self.assertTrue(should_deploy(None, "workflow_dispatch", "main"))
        self.assertTrue(should_deploy(None, "workflow_dispatch", "beta"))

    def test_docs_do_not_require_backend_or_registry(self):
        selected = select_jobs(
            ["docs/help.md"], pull("content", "fix", True), "pull_request", ""
        )
        self.assertEqual({k for k, v in selected.items() if v}, {"documentation"})

    def test_unknown_change_and_workflow_change_run_everything(self):
        for files in [
            None,
            ["unknown.config"],
            [".github/workflows/ci.yml"],
            [".github/workflows/unknown.yml"],
            [".github/actions/unknown/action.yml"],
            ["package-lock.json"],
        ]:
            self.assertEqual(
                select_jobs(files, {}, "push", "dev"),
                {job: job != "blueprints" for job in JOBS},
            )

    def test_runtime_and_blueprints(self):
        self.assertTrue(
            select_jobs(["custom_components/f1_sensor/auth.py"], {}, "push", "dev")[
                "backend"
            ]
        )
        selected = select_jobs(["blueprints/example.yaml"], {}, "push", "content")
        self.assertTrue(selected["blueprints"])
        self.assertFalse(selected["backend"])

    def test_promotions_use_the_same_impact_contract_as_development(self):
        for base, head in [("beta", "dev"), ("main", "beta")]:
            self.assertEqual(
                select_jobs(["docs/help.md"], pull(base, head), "pull_request", ""),
                {job: job == "documentation" for job in JOBS},
            )
            self.assertEqual(
                select_jobs(["docs/help.md"], {}, "push", base),
                {job: job == "documentation" for job in JOBS},
            )
            runtime = select_jobs(
                ["custom_components/f1_sensor/coordinator.py"],
                pull(base, head),
                "pull_request",
                "",
            )
            self.assertEqual(
                {job for job, enabled in runtime.items() if enabled},
                {
                    "lint",
                    "backend",
                    "frontend",
                    "translations",
                    "validation",
                    "package",
                },
            )
            self.assertFalse(runtime["documentation"])
            self.assertFalse(runtime["audit"])

    def test_issue_metadata_changes_do_not_run_product_browsers_or_security(self):
        for path in (
            ".github/scripts/issue-automation.cjs",
            ".github/workflows/issue-version-check.yml",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            "ci_tests/issues.test.cjs",
        ):
            for branch in ("dev", "beta", "main"):
                with self.subTest(path=path, branch=branch):
                    selected = select_jobs([path], {}, "push", branch)
                    self.assertEqual(
                        {job for job, enabled in selected.items() if enabled},
                        {"automation"},
                    )

    def test_audit_evaluator_changes_keep_full_security_enforcement(self):
        for path in (
            "scripts/npm_audit_semver.cjs",
            ".github/workflows/security-health.yml",
            ".github/workflows/security-snapshot.yml",
        ):
            with self.subTest(path=path):
                files = [path]
                selected = select_jobs(files, pull("beta", "dev"), "pull_request", "")
                self.assertTrue(selected["audit"])
                self.assertTrue(selected["automation"])
                self.assertEqual(
                    audit_context(pull("beta", "dev"), "pull_request", "", files),
                    ("gate", ""),
                )

    def test_only_release_executions_may_delegate_docs_and_full_security(self):
        selected = select_jobs(None, {}, "workflow_dispatch", "beta")
        product = release_product_checks(
            selected, separate_delivery=True, event_name="push", branch="beta"
        )
        self.assertFalse(product["documentation"])
        self.assertFalse(product["audit"])
        for job in ("backend", "frontend", "validation", "package"):
            self.assertTrue(product[job])
        self.assertTrue(selected["documentation"])
        self.assertTrue(selected["audit"])
        for event, branch in (("pull_request", "beta"), ("push", "dev")):
            with (
                self.subTest(event=event, branch=branch),
                self.assertRaises(ValueError),
            ):
                release_product_checks(
                    selected, separate_delivery=True, event_name=event, branch=branch
                )

    def test_dev_verification_only_is_limited_to_an_explicit_manual_dry_run(self):
        selected = select_jobs(None, {}, "workflow_dispatch", "dev")
        product = release_product_checks(
            selected,
            separate_delivery=True,
            event_name="workflow_dispatch",
            branch="dev",
            verification_only=True,
        )
        self.assertFalse(product["documentation"])
        self.assertFalse(product["audit"])
        for job in ("backend", "frontend", "validation", "package"):
            self.assertTrue(product[job])
        self.assertTrue(selected["documentation"])
        self.assertTrue(selected["audit"])
        for event, branch, verification_only in (
            ("push", "dev", True),
            ("pull_request", "dev", True),
            ("workflow_dispatch", "content", True),
            ("workflow_dispatch", "dev", False),
            ("workflow_dispatch", "dev", "false"),
        ):
            with (
                self.subTest(event=event, branch=branch, flag=verification_only),
                self.assertRaises(ValueError),
            ):
                release_product_checks(
                    selected,
                    separate_delivery=True,
                    event_name=event,
                    branch=branch,
                    verification_only=verification_only,
                )

    def test_plan_accepts_explicit_false_and_keeps_immutable_delivery_inputs(self):
        for release in (False, "false"):
            with (
                self.subTest(release=release),
                tempfile.TemporaryDirectory() as directory,
            ):
                event = Path(directory) / "event.json"
                output = Path(directory) / "output.txt"
                event.write_text(json.dumps({"inputs": {"release": release}}))
                with (
                    patch.dict(
                        os.environ,
                        {
                            "GITHUB_EVENT_PATH": str(event),
                            "GITHUB_OUTPUT": str(output),
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                            "GITHUB_REF_NAME": "dev",
                            "CI_SEPARATE_DELIVERY": "true",
                        },
                    ),
                    patch.object(sys, "argv", ["ci_policy.py", "plan"]),
                    patch("scripts.ci_policy.changed_files", return_value=None),
                    patch(
                        "scripts.ci_policy.subprocess.check_output",
                        side_effect=["a" * 40, "b" * 40],
                    ),
                ):
                    self.assertEqual(main(), 0)
                values = dict(
                    line.split("=", 1) for line in output.read_text().splitlines()
                )
                self.assertEqual(values["tested_sha"], "a" * 40)
                self.assertEqual(values["tested_tree"], "b" * 40)
                self.assertEqual(values["audit_mode"], "gate")
                self.assertEqual(values["deploy"], "false")
                selected = json.loads(values["selected"])
                self.assertFalse(selected["documentation"])
                self.assertFalse(selected["audit"])

    def test_dev_plan_rejects_missing_default_true_and_other_release_input_values(self):
        for inputs in (
            {},
            {"release": True},
            {"release": "true"},
            {"release": 0},
            {"release": None},
            {"release": "False"},
        ):
            with (
                self.subTest(inputs=inputs),
                tempfile.TemporaryDirectory() as directory,
            ):
                event = Path(directory) / "event.json"
                event.write_text(json.dumps({"inputs": inputs}))
                with (
                    patch.dict(
                        os.environ,
                        {
                            "GITHUB_EVENT_PATH": str(event),
                            "GITHUB_EVENT_NAME": "workflow_dispatch",
                            "GITHUB_REF_NAME": "dev",
                            "CI_SEPARATE_DELIVERY": "true",
                        },
                    ),
                    patch.object(sys, "argv", ["ci_policy.py", "plan"]),
                    patch("scripts.ci_policy.changed_files", return_value=None),
                    self.assertRaises(ValueError),
                ):
                    main()

    def test_dependency_changes_are_audited_before_and_after_merge(self):
        for base in ("dev", "content", "beta", "main"):
            for fork in (False, True):
                event = pull(base, "change", fork)
                for files in (None, ["package-lock.json"], ["unknown.config"]):
                    for trigger in ("pull_request", "workflow_dispatch"):
                        with self.subTest(
                            base=base, fork=fork, files=files, trigger=trigger
                        ):
                            self.assertTrue(
                                select_jobs(files, event, trigger, base)["audit"]
                            )
        for branch in ("dev", "content"):
            self.assertTrue(select_jobs(None, {}, "push", branch)["audit"])

    def test_valid_target_catalog_changes_use_only_translation_contract(self):
        files = [
            "custom_components/f1_sensor/translations/sv.json",
            "custom_components/f1_sensor/www/f1-sensor-live-data-card/localization/locales/pt-BR.json",
        ]
        for event_name in ("push", "pull_request"):
            selected = select_jobs(files, {}, event_name, "dev")
            self.assertEqual(
                {k for k, enabled in selected.items() if enabled}, {"translations"}
            )
        for extra in (
            "custom_components/f1_sensor/translations/en.json",
            "custom_components/f1_sensor/auth.py",
            "custom_components/f1_sensor/www/f1-sensor-live-data-card/localization/index.js",
            "custom_components/f1_sensor/translations/invalid_name.json",
        ):
            selected = select_jobs([*files, extra], {}, "push", "dev")
            self.assertTrue(selected["backend"])
            self.assertTrue(selected["frontend"])

    def test_security_scope_is_identical_for_preflight_and_release_targets(self):
        self.assertEqual(
            audit_context(
                pull("dev", "deps"), "pull_request", "", ["package-lock.json"]
            ),
            ("introduced", "a" * 40),
        )
        self.assertEqual(
            audit_context({"before": "c" * 40}, "push", "dev", ["package-lock.json"]),
            ("introduced", "c" * 40),
        )
        for base, head in [("beta", "dev"), ("main", "beta")]:
            self.assertEqual(
                audit_context(
                    pull(base, head), "pull_request", "", ["package-lock.json"]
                ),
                ("introduced", "a" * 40),
            )
            self.assertEqual(
                audit_context(
                    {"before": "c" * 40}, "push", base, ["package-lock.json"]
                ),
                ("introduced", "c" * 40),
            )
        for event, trigger, branch in (
            (pull("beta", "dev"), "pull_request", ""),
            (pull("main", "beta"), "pull_request", ""),
            ({}, "push", "beta"),
            ({}, "workflow_dispatch", "dev"),
            ({"before": "0" * 40}, "push", "dev"),
        ):
            self.assertEqual(audit_context(event, trigger, branch), ("gate", ""))
        self.assertEqual(
            audit_context(pull("dev", "deps"), "pull_request", "", None), ("gate", "")
        )
        self.assertEqual(
            audit_context(
                pull("dev", "policy"),
                "pull_request",
                "",
                ["quality/npm-audit-policy.json"],
            ),
            ("gate", ""),
        )

    def test_release_and_maintenance_audit_selection_is_preserved(self):
        for trigger, branch in (
            ("push", "main"),
            ("push", "beta"),
            ("workflow_dispatch", "main"),
            ("workflow_dispatch", "beta"),
            ("schedule", "main"),
        ):
            with self.subTest(trigger=trigger, branch=branch):
                self.assertTrue(select_jobs(None, {}, trigger, branch)["audit"])

    def test_branch_routing_including_forks_and_retarget(self):
        self.assertFalse(
            branch_error(
                pull("dev", "fix", True), ["custom_components/f1_sensor/auth.py"]
            )
        )
        self.assertFalse(branch_error(pull("main", "beta"), ["code.py"]))
        self.assertTrue(branch_error(pull("main", "beta", True), ["code.py"]))
        self.assertTrue(
            branch_error(pull("content", "fix"), ["docs/help.md", "code.py"])
        )
        self.assertTrue(branch_error(pull("main", "content"), ["code.py"]))
        self.assertFalse(branch_error(pull("main", "content"), ["docs/help.md"]))
        self.assertFalse(
            branch_error(
                pull("main", "content"),
                [
                    "docusaurus.config.js",
                    "src/css/custom.css",
                    "ci_tests/documentation_channels.test.mjs",
                ],
            )
        )
        self.assertTrue(
            branch_error(
                pull("main", "content"),
                [".github/workflows/documentation.yml"],
            )
        )

    def test_gate_accepts_only_verified_reuse_and_requires_actual_skip(self):
        selected = dict.fromkeys(JOBS, False)
        selected["backend"] = True
        results = {job: {"result": "skipped"} for job in JOBS}
        self.assertTrue(gate_errors(selected, results))
        self.assertEqual(gate_errors(selected, results, ["backend"]), [])
        results["backend"] = {"result": "failure"}
        self.assertTrue(gate_errors(selected, results, ["backend"]))

    def test_aggregate_fails_for_missing_cancelled_or_unexpected_skips(self):
        selected = dict.fromkeys(JOBS, True)
        results = {j: {"result": "success"} for j in JOBS}
        self.assertEqual(gate_errors(selected, results), [])
        for result in ["failure", "cancelled", "skipped", "missing"]:
            results["backend"] = {"result": result}
            self.assertTrue(gate_errors(selected, results))
        selected["backend"] = False
        results["backend"] = {"result": "skipped"}
        self.assertEqual(gate_errors(selected, results), [])


if __name__ == "__main__":
    unittest.main()
