#!/usr/bin/env python3
"""Reuse fresh, trusted push checks; never trust artifacts or PR-supplied claims."""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REUSABLE = {
    "lint": ["checks / lint / ruff"],
    "backend": ["checks / backend / HA minimum", "checks / backend / HA current"],
    "frontend": ["checks / frontend / frontend"],
    "documentation": ["checks / documentation / documentation"],
    "package": ["checks / package / package"],
    "automation": ["checks / automation / automation"],
}


class GitHub:
    def __init__(self):
        self.repo = os.environ["GITHUB_REPOSITORY"]

    def get(self, path):
        request = Request(
            f"https://api.github.com/repos/{self.repo}/{path}",
            headers={
                "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.load(response)

    def jobs(self, run_id):
        jobs = []
        for page in range(1, 11):
            result = self.get(f"actions/runs/{run_id}/jobs?per_page=100&page={page}")
            jobs.extend(result["jobs"])
            if len(jobs) >= result["total_count"]:
                return jobs
        raise ValueError("Incomplete job evidence")


def eligible_run(run, now):
    try:
        age = now - datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        return (
            run["event"] == "push"
            and run["path"] == ".github/workflows/development.yml"
            and run["head_branch"] in ("dev", "content")
            and re.fullmatch(r"[0-9a-f]{40}", run["head_sha"]) is not None
            and run["status"] == "completed"
            and run["conclusion"] == "success"
            and timedelta(0) <= age <= timedelta(hours=2)
        )
    except (KeyError, TypeError, ValueError):
        return False


def successful_checks(jobs):
    results = {job["name"]: job.get("conclusion") for job in jobs}
    return {
        key
        for key, names in REUSABLE.items()
        if all(results.get(name) == "success" for name in names)
    }


def evidence_checks(api, run, tree, now):
    if not eligible_run(run, now):
        return set()
    # A Git tree includes every workflow, lockfile, test, source and profile.
    if api.get(f"git/commits/{run['head_sha']}")["tree"]["sha"] != tree:
        return set()
    jobs = api.jobs(run["id"])
    if not any(
        j["name"] == "checks / Verify selected checks"
        and j.get("conclusion") == "success"
        for j in jobs
    ):
        return set()
    return successful_checks(jobs)


def find_evidence(api, selected, tree, now):
    runs = api.get(
        "actions/workflows/development.yml/runs?"
        + urlencode(
            {
                "event": "push",
                "status": "success",
                "per_page": 30,
            }
        )
    )["workflow_runs"]
    for run in runs:
        checks = sorted(
            key for key in evidence_checks(api, run, tree, now) if selected.get(key)
        )
        if checks:
            return {
                "run_id": run["id"],
                "attempt": run["run_attempt"],
                "head_sha": run["head_sha"],
                "checks": checks,
            }
    return {}


def verify_evidence(api, evidence, tree, now):
    if not evidence:
        return
    run = api.get(f"actions/runs/{int(evidence['run_id'])}")
    checks = set(evidence["checks"])
    if (
        run["head_sha"] != evidence["head_sha"]
        or run["run_attempt"] != evidence["attempt"]
        or not checks
        or not checks <= evidence_checks(api, run, tree, now)
    ):
        raise ValueError("Reused check evidence changed or expired; rerun CI")


def main():
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    now = datetime.now(UTC)
    api = GitHub()
    if sys.argv[1] == "verify":
        verify_evidence(api, json.loads(os.environ.get("CI_REUSED", "{}")), tree, now)
        return
    selected = json.loads(os.environ["CI_SELECTED"])
    evidence = {}
    # Release, maintenance, forks' dispatches and manual retries run their own checks.
    if (
        os.environ.get("CI_ALLOW_REUSE") == "true"
        and os.environ["GITHUB_EVENT_NAME"] == "pull_request"
    ):
        try:
            evidence = find_evidence(api, selected, tree, now)
        except Exception as error:  # Optimization failure must never block fresh tests.
            print(
                f"Reuse unavailable; running applicable tests: {type(error).__name__}"
            )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"reused={json.dumps(evidence)}\n")
        for key, enabled in selected.items():
            output.write(
                f"{key}={str(enabled and key not in evidence.get('checks', [])).lower()}\n"
            )
    if evidence:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
            summary.write(
                "Reused verified checks for the identical Git tree: "
                + ", ".join(evidence["checks"])
                + f". [Source run](https://github.com/{api.repo}/actions/runs/{evidence['run_id']}).\n"
            )


if __name__ == "__main__":
    main()
