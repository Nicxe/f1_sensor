#!/usr/bin/env python3
"""Select checks and enforce branch policy without network access or secrets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

JOBS = (
    "lint",
    "backend",
    "frontend",
    "documentation",
    "validation",
    "package",
    "audit",
    "blueprints",
    "automation",
)
RUNTIME = {"lint", "backend", "frontend", "validation", "package"}


def content_only(files: list[str]) -> bool:
    return bool(files) and all(p.startswith(("docs/", "blueprints/")) for p in files)


def branch_error(event: dict, files: list[str]) -> str:
    pr = event.get("pull_request")
    if not pr:
        return ""
    base, head = pr["base"]["ref"], pr["head"]["ref"]
    same_repo = (
        pr["head"].get("repo", {}).get("full_name") == pr["base"]["repo"]["full_name"]
    )
    # Synchronization snapshots are created only in this repository by its bot.
    sync = (
        same_repo
        and pr["user"]["login"] == "github-actions[bot]"
        and head.startswith("sync/")
    )
    if sync and base in ("dev", "beta", "content"):
        return ""
    if base == "dev":
        return (
            "Use content for standalone docs/blueprints." if content_only(files) else ""
        )
    if base == "content":
        return (
            ""
            if content_only(files)
            else "Only docs/** and blueprints/** belong on content; use dev for code."
        )
    if same_repo and (
        (base == "beta" and head == "dev") or (base == "main" and head == "beta")
    ):
        return ""
    if same_repo and base == "main" and head == "content" and content_only(files):
        return ""
    return "Code follows dev → beta → main. Standalone docs/blueprints follow content → main."


def select_jobs(
    files: list[str] | None, event: dict, event_name: str, branch: str
) -> dict[str, bool]:
    pr = event.get("pull_request", {})
    promotion = (
        pr.get("base", {}).get("ref") in ("beta", "main")
        and pr.get("head", {}).get("ref") != "content"
    )
    if (
        files is None
        or event_name in ("workflow_dispatch", "schedule")
        or promotion
        or (event_name == "push" and branch in ("beta", "main"))
    ):
        return dict.fromkeys(JOBS, True)
    selected = {"automation"}
    for path in files:
        if path.startswith(
            (".github/", "scripts/", "ci_tests/", "quality/", "requirements")
        ) or path in (
            "package.json",
            "package-lock.json",
            "pyproject.toml",
            "conftest.py",
            "release.config.js",
            "release.config.cjs",
        ):
            selected.update(JOBS)
        elif path.startswith("blueprints/"):
            selected.update(("blueprints", "documentation"))
        elif (
            path.startswith(("docs/", "src/", "static/", "docs-tests/"))
            or path.startswith(("docusaurus.config.", "sidebars.", "playwright.docs."))
            or path.endswith(".md")
        ):
            selected.add("documentation")
        elif path.startswith(("frontend-tests/", "playwright.config.")):
            selected.add("frontend")
        elif path.startswith("custom_components/") or path == "hacs.json":
            selected.update(RUNTIME)
        elif path.startswith("patches/"):
            selected.update(JOBS)
        elif path not in ("LICENSE", ".gitignore"):
            selected.update(JOBS)
    return {job: job in selected for job in JOBS}


def gate_errors(selected: dict, results: dict) -> list[str]:
    errors = []
    for job in JOBS:
        actual = results.get(job, {}).get("result", "missing")
        expected = "success" if selected.get(job) else "skipped"
        if actual != expected:
            errors.append(f"{job}: expected {expected}, got {actual}")
    return errors


def changed_files(event: dict, event_name: str) -> list[str] | None:
    try:
        if event_name == "pull_request":
            pr = event["pull_request"]
            args = [f"{pr['base']['sha']}...{pr['head']['sha']}"]
        elif event_name == "push" and set(event.get("before", "0")) != {"0"}:
            args = [event["before"], event["after"]]
        else:
            return None
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", "-z", *args],
            check=True,
            capture_output=True,
        )
        return [p for p in result.stdout.decode().split("\0") if p]
    except (subprocess.CalledProcessError, KeyError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "gate"))
    args = parser.parse_args()
    if args.mode == "gate":
        results = json.loads(os.environ["CI_NEEDS"])
        if results.get("plan", {}).get("result") != "success":
            print("CI selection/branch policy failed")
            return 1
        errors = gate_errors(
            json.loads(results["plan"]["outputs"]["selected"]), results
        )
        print("\n".join(errors) if errors else "All applicable checks passed")
        return int(bool(errors))
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    name = os.environ["GITHUB_EVENT_NAME"]
    dispatched_pr = event.get("inputs", {}).get("pull_request", "")
    if dispatched_pr:
        if not str(dispatched_pr).isdigit():
            raise ValueError("invalid pull request number")
        request = Request(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/pulls/{dispatched_pr}",
            headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}"},
        )
        with urlopen(request, timeout=20) as response:
            pr = json.load(response)
        if pr["head"]["sha"] != os.environ["GITHUB_SHA"]:
            raise ValueError("PR head changed; dispatch a new check for its exact head")
        event = {"pull_request": pr}
        name = "pull_request"
    files = changed_files(event, name)
    error = branch_error(event, files or [])
    if error:
        print(error)
        return 1
    selected = select_jobs(files, event, name, os.environ.get("GITHUB_REF_NAME", ""))
    print(json.dumps({"files": files, "checks": selected}, indent=2))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"selected={json.dumps(selected)}\n")
        for job, enabled in selected.items():
            output.write(f"{job}={str(enabled).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
