"""Acceptance cases for required checks and branch routing."""

import unittest

from scripts.ci_policy import JOBS, branch_error, gate_errors, select_jobs


def pull(base, head, fork=False):
    return {
        "pull_request": {
            "base": {"ref": base, "repo": {"full_name": "Nicxe/f1_sensor"}},
            "head": {
                "ref": head,
                "repo": {"full_name": "fork/repo" if fork else "Nicxe/f1_sensor"},
            },
            "user": {"login": "contributor"},
        }
    }


class PolicyTests(unittest.TestCase):
    def test_docs_do_not_require_backend_or_registry(self):
        selected = select_jobs(
            ["docs/help.md"], pull("content", "fix", True), "pull_request", ""
        )
        self.assertEqual(
            {k for k, v in selected.items() if v}, {"automation", "documentation"}
        )

    def test_unknown_change_and_workflow_change_run_everything(self):
        for files in [
            None,
            ["unknown.config"],
            [".github/workflows/ci.yml"],
            ["package-lock.json"],
        ]:
            self.assertTrue(all(select_jobs(files, {}, "push", "dev").values()))

    def test_runtime_and_blueprints(self):
        self.assertTrue(
            select_jobs(["custom_components/f1_sensor/auth.py"], {}, "push", "dev")[
                "backend"
            ]
        )
        selected = select_jobs(["blueprints/example.yaml"], {}, "push", "content")
        self.assertTrue(selected["blueprints"])
        self.assertFalse(selected["backend"])

    def test_promotions_and_final_commits_always_run_all(self):
        for base, head in [("beta", "dev"), ("main", "beta")]:
            self.assertTrue(
                all(
                    select_jobs(
                        ["docs/help.md"], pull(base, head), "pull_request", ""
                    ).values()
                )
            )
            self.assertTrue(
                all(select_jobs(["docs/help.md"], {}, "push", base).values())
            )

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
