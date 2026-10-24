#!/usr/bin/env python3
"""Select checks and enforce branch policy without network access or secrets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

JOBS = (
    "lint",
    "backend",
    "frontend",
    "translations",
    "documentation",
    "validation",
    "package",
    "audit",
    "blueprints",
    "automation",
)
RUNTIME = {"lint", "backend", "frontend", "translations", "validation", "package"}
SHARED_POLICY = {
    "scripts/ci_policy.py",
    "scripts/ci_reuse.py",
    "scripts/verification.py",
    "scripts/verify_dev.py",
    "scripts/run_check.py",
    "scripts/ci_environment.py",
    "scripts/setup_ci_environment.py",
    "ci_tests/test_ci_policy.py",
    "ci_tests/test_ci_reuse.py",
    "ci_tests/test_verify_dev.py",
    ".github/workflows/ci-checks.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/development.yml",
    ".github/workflows/release-pipeline.yml",
}
AUDIT_POLICY = {
    "quality/npm-audit-policy.json",
    "quality/npm-audit-allowlist.json",
    "scripts/check_npm_audit.py",
    "scripts/run_npm_audit.py",
    "scripts/npm_audit_semver.cjs",
    ".github/workflows/audit.yml",
    ".github/workflows/security-health.yml",
}
DOCUMENTATION_WORKFLOWS = {
    ".github/workflows/documentation.yml",
    ".github/workflows/documentation-publication.yml",
    ".github/workflows/deploy.yml",
}
AUTOMATION_WORKFLOWS = {
    ".github/workflows/automation-tests.yml",
    ".github/workflows/cleanup-merged-branches.yml",
    ".github/workflows/issue-component-labeler.yml",
    ".github/workflows/issue-release-comment.yml",
    ".github/workflows/issue-version-check.yml",
    ".github/workflows/maintenance.yml",
    ".github/workflows/pr-target-check.yml",
    ".github/workflows/release.yml",
    ".github/workflows/sync-after-release.yml",
}
TARGET_TRANSLATION = re.compile(
    r"^custom_components/f1_sensor/(?:translations/|"
    r"www/f1-sensor-live-data-card/localization/locales/)"
    r"(?!en\.json$)[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\.json$"
)
STABLE_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RELEASE_TRIGGER = re.compile(r"^(?:feat|fix)(?:\([^)]+\))?!?:")
RELEASE_POLICY_PATH = Path(__file__).parents[1] / "semantic-release-policy.json"


def selected_checks(selected: set[str], *, audit: bool = True) -> dict[str, bool]:
    """Backend profiles already include the blueprint tests."""
    return {
        job: job in selected
        and not (job == "blueprints" and "backend" in selected)
        and (job != "audit" or audit)
        for job in JOBS
    }


def should_deploy(files: list[str] | None, event_name: str, branch: str) -> bool:
    """A full release test run does not imply that the site needs deployment."""
    if branch not in ("main", "beta") or event_name not in (
        "push",
        "workflow_dispatch",
    ):
        return False
    if files is None:
        return True
    return any(
        path.startswith(
            (
                "docs/",
                "blueprints/",
                "src/",
                "static/",
                "docs-tests/",
                "patches/",
                ".github/workflows/",
            )
        )
        or path.endswith(".md")
        or path.startswith(("docusaurus.config.", "sidebars.", "playwright.docs."))
        or path in ("package.json", "package-lock.json")
        for path in files
    )


def content_only(files: list[str]) -> bool:
    """Return whether a change is limited to published documentation content."""
    return bool(files) and all(
        p.startswith(("docs/", "blueprints/", "src/", "static/", "docs-tests/"))
        or p
        in (
            "docusaurus.config.js",
            "sidebars.js",
            "playwright.docs.config.js",
            "ci_tests/documentation_channels.test.mjs",
        )
        for p in files
    )


def hotfix_matches_dev(files: list[str], *, base_sha: str, head_sha: str) -> bool:
    """Require every beta hotfix commit to match a patch already on dev."""
    if not files or not all(
        isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
        for sha in (base_sha, head_sha)
    ):
        return False
    commits = subprocess.run(
        ["git", "rev-list", f"{base_sha}..{head_sha}"],
        capture_output=True,
        check=False,
        text=True,
    )
    cherry = subprocess.run(
        ["git", "cherry", "origin/dev", head_sha, base_sha],
        capture_output=True,
        check=False,
        text=True,
    )
    if commits.returncode or cherry.returncode:
        return False
    expected = set(commits.stdout.splitlines())
    checked = cherry.stdout.splitlines()
    return (
        bool(expected)
        and len(checked) == len(expected)
        and all(line.startswith("- ") and line[2:] in expected for line in checked)
    )


def latest_stable_release_tag(commit: str) -> str | None:
    """Return semantic-release's latest stable tag reachable from ``commit``."""
    result = subprocess.run(
        ["git", "tag", "--merged", commit],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("could not inspect release tags")
    tags = []
    for tag in result.stdout.splitlines():
        match = STABLE_RELEASE_TAG.fullmatch(tag)
        if match:
            tags.append((tuple(map(int, match.groups())), tag))
    return max(tags, default=(None, None))[1]


def non_releasing_commit_headers() -> set[str]:
    """Read the exact semantic-release exclusions used by release.config.cjs."""
    try:
        policy = json.loads(RELEASE_POLICY_PATH.read_text())
        rules = policy["nonReleaseRules"]
        if not isinstance(rules, list):
            raise TypeError("nonReleaseRules is not a list")
        headers = {
            f"{rule['type']}({rule['scope']}): {rule['subject']}"
            for rule in rules
            if rule.get("release") is False
            and isinstance(rule.get("type"), str)
            and isinstance(rule.get("scope"), str)
            and isinstance(rule.get("subject"), str)
        }
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"could not read semantic-release policy: {error}"
        ) from error
    return headers


def release_triggering_commits(commit_range: str) -> list[tuple[str, str]]:
    """List feat/fix commits in a range, as semantic-release would consider them."""
    result = subprocess.run(
        ["git", "log", "--format=%H%x00%s", commit_range],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("could not inspect release commits")
    excluded_headers = non_releasing_commit_headers()
    commits = []
    for line in result.stdout.splitlines():
        sha, separator, subject = line.partition("\x00")
        if (
            separator
            and RELEASE_TRIGGER.match(subject)
            and subject not in excluded_headers
        ):
            commits.append((sha, subject))
    return commits


def main_promotion_release_error(event: dict) -> str:
    """Reject a beta promotion when main already has unreleased feat/fix history.

    semantic-release analyzes all commits since its latest stable tag, not only
    the pull request diff. A reverted accidental merge remains in Git history,
    so this check makes that unsafe state visible before another beta promotion
    can generate a misleading stable release.
    """
    pr = event.get("pull_request")
    if not pr:
        return ""
    base, head = pr["base"], pr["head"]
    same_repo = head.get("repo", {}).get("full_name") == base["repo"]["full_name"]
    if not (same_repo and base["ref"] == "main" and head["ref"] == "beta"):
        return ""
    try:
        tag = latest_stable_release_tag(base["sha"])
        if tag is None:
            return "Main has no stable semantic-release baseline tag."
        inherited = release_triggering_commits(f"{tag}..{base['sha']}")
    except RuntimeError as error:
        return f"Could not verify the semantic-release boundary: {error}."
    if not inherited:
        return ""
    subjects = ", ".join(f"{sha[:7]} {subject}" for sha, subject in inherited[:3])
    extra = "" if len(inherited) <= 3 else f" (+{len(inherited) - 3} more)"
    return (
        f"Main already has {len(inherited)} unreleased feat/fix commit(s) since {tag} "
        f"before this beta promotion: {subjects}{extra}. Establish or repair the "
        "semantic-release baseline before merging so the draft contains only the "
        "intended release changes."
    )


def branch_error(event: dict, files: list[str]) -> str:
    pr = event.get("pull_request")
    if not pr:
        return ""
    base, head = pr["base"]["ref"], pr["head"]["ref"]
    same_repo = (
        pr["head"].get("repo", {}).get("full_name") == pr["base"]["repo"]["full_name"]
    )
    owner = pr["base"].get("repo", {}).get("full_name", "").split("/", 1)[0]
    author = pr.get("user", {}).get("login", "")
    # Repository-owned PRs may target a branch that fits the maintainer's
    # work. Branch protections and release verification remain independent.
    if same_repo and owner and author.casefold() == owner.casefold():
        return ""
    # Synchronization snapshots are created only in this repository by its bot.
    sync = (
        same_repo
        and pr["user"]["login"] == "github-actions[bot]"
        and head.startswith("sync/")
    )
    if sync and base in ("dev", "beta", "content"):
        return ""
    # The repository owner can repair dependency/CI infrastructure on main
    # without promoting unreleased integration changes from dev. Required CI
    # and PR protection still apply; this does not grant automatic merging.
    maintenance_files = bool(files) and all(
        p
        in (
            "CONTRIBUTING.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "package.json",
            "package-lock.json",
            ".github/dependabot.yml",
            "quality/npm-audit-allowlist.json",
            "scripts/ci_policy.py",
            "scripts/check_npm_audit.py",
            "scripts/run_npm_audit.py",
        )
        or p.startswith((".github/workflows/", ".github/scripts/", "ci_tests/"))
        for p in files
    )
    if (
        same_repo
        and base == "main"
        and head.startswith("maintenance/")
        and pr["user"]["login"] == pr["base"]["repo"]["full_name"].split("/")[0]
        and maintenance_files
    ):
        return ""
    # Dependency PRs may target the default branch for security fixes. The
    # trusted auto-merge workflow separately verifies signed Dependabot commits
    # and a matching open security alert before enabling automatic merging.
    dependency_files = bool(files) and all(
        p in ("package.json", "package-lock.json")
        or (p.startswith("requirements/") and p.endswith(".txt"))
        or (p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")))
        for p in files
    )
    if (
        same_repo
        and base == "main"
        and head.startswith("dependabot/")
        and pr["user"]["login"] == "dependabot[bot]"
        and dependency_files
    ):
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
    if (
        same_repo
        and base == "beta"
        and head.startswith("hotfix/")
        and pr["user"]["login"] == pr["base"]["repo"]["full_name"].split("/")[0]
    ):
        return (
            ""
            if hotfix_matches_dev(
                files, base_sha=pr["base"]["sha"], head_sha=pr["head"]["sha"]
            )
            else "Every beta hotfix commit must match a commit already on dev."
        )
    if same_repo and base == "main" and head == "content" and content_only(files):
        return ""
    return "Code follows dev → beta → main. Standalone docs/blueprints follow content → main."


def select_jobs(
    files: list[str] | None, event: dict, event_name: str, branch: str
) -> dict[str, bool]:
    if files is None or event_name in ("workflow_dispatch", "schedule"):
        return selected_checks(set(JOBS))
    if files and all(TARGET_TRANSLATION.fullmatch(path) for path in files):
        return selected_checks({"translations"})
    selected: set[str] = set()
    for path in files:
        if (
            path in SHARED_POLICY
            or path.startswith("requirements/")
            or path
            in (
                "package.json",
                "package-lock.json",
                "pyproject.toml",
                "conftest.py",
                ".node-version",
                ".python-version",
                ".npmrc",
            )
        ):
            selected.update(JOBS)
        elif path in AUDIT_POLICY:
            selected.update(("lint", "automation", "audit"))
        elif (
            path in DOCUMENTATION_WORKFLOWS
            or path == "ci_tests/documentation_channels.test.mjs"
            or path.startswith(
                (".github/scripts/documentation-", "ci_tests/documentation-")
            )
        ):
            selected.update(("automation", "documentation"))
        elif path in ("scripts/check_coverage.py", "quality/coverage-ratchet.json"):
            selected.update(("lint", "backend", "automation"))
        elif path in (
            "scripts/run_ci_tests.py",
            "scripts/run_tests.sh",
            "scripts/test_installed_release.py",
            ".github/workflows/tests.yml",
        ) or path.startswith(("tests/", "ci_smoke/")):
            selected.update(("lint", "backend", "validation", "package"))
        elif path in (
            "scripts/check_translations.py",
            ".github/workflows/translations.yml",
        ):
            selected.update(("lint", "translations", "automation"))
        elif path in (
            "scripts/check_manifest.py",
            "scripts/check_localization.py",
            "scripts/check_release_build.py",
            "scripts/build_release.py",
            ".github/workflows/package.yml",
        ):
            selected.update(("lint", "package", "automation"))
        elif path == ".github/workflows/ruff.yml":
            selected.update(("lint", "automation"))
        elif path == ".github/workflows/validate.yml":
            selected.update(("validation", "automation"))
        elif path == ".github/workflows/frontend.yml":
            selected.update(("frontend", "automation"))
        elif path in (
            "release.config.js",
            "release.config.cjs",
            "semantic-release-policy.json",
        ):
            selected.update(("automation", "package", "audit"))
        elif (
            path in AUTOMATION_WORKFLOWS
            or path == ".github/PULL_REQUEST_TEMPLATE.md"
            or path.startswith(
                (".github/scripts/", ".github/ISSUE_TEMPLATE/", "ci_tests/")
            )
        ):
            # Issue/PR metadata, branch synchronization and release automation
            # have executable contract tests, but do not change HA or browsers.
            selected.add("automation")
            if path.endswith(".py"):
                selected.add("lint")
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
    return selected_checks(selected)


def audit_context(
    event: dict, event_name: str, branch: str, files: list[str] | None = None
) -> tuple[str, str]:
    """Ordinary changes block new risks; complete release readiness is separate."""
    if files is None:
        return "gate", ""
    if files and any(path in AUDIT_POLICY for path in files):
        return "gate", ""
    pr = event.get("pull_request")
    if pr:
        return "introduced", pr["base"]["sha"]
    if event_name == "push" and branch in ("dev", "content", "beta", "main"):
        base = event.get("before", "")
        if re.fullmatch(r"[0-9a-f]{40}", base) and set(base) != {"0"}:
            return "introduced", base
    return "gate", ""


def release_product_checks(
    selected: dict[str, bool], *, separate_delivery: bool, event_name: str, branch: str
) -> dict[str, bool]:
    """Only trusted release executions may delegate docs and full security."""
    selected = dict(selected)
    if separate_delivery:
        if event_name not in ("push", "workflow_dispatch") or branch not in (
            "beta",
            "main",
        ):
            raise ValueError(
                "Separate delivery is restricted to trusted beta/main release executions"
            )
        selected["documentation"] = False
        selected["audit"] = False
    return selected


def gate_errors(selected: dict, results: dict, reused=()) -> list[str]:
    errors = []
    for job in JOBS:
        actual = results.get(job, {}).get("result", "missing")
        expected = "success" if selected.get(job) and job not in reused else "skipped"
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
            if os.environ.get("GITHUB_OUTPUT"):
                with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                    output.write("result=failure\n")
            print("CI selection/branch policy failed")
            return 1
        evidence = json.loads(results["plan"]["outputs"].get("reused", "{}"))
        if evidence:
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("ci_reuse.py")),
                    "verify",
                ],
                env={**os.environ, "CI_REUSED": json.dumps(evidence)},
                check=True,
            )
        errors = gate_errors(
            json.loads(results["plan"]["outputs"]["selected"]),
            results,
            evidence.get("checks", []),
        )
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with Path(summary_path).open("a") as summary:
                summary.write("## Verification result\n\n")
                summary.write(
                    "All selected checks passed.\n"
                    if not errors
                    else "The following checks need attention; aggregate failures are consequences of these results.\n\n"
                    + "\n".join(f"- {error}" for error in errors)
                    + "\n"
                )
        print("\n".join(errors) if errors else "All applicable checks passed")
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                output.write(f"result={'failure' if errors else 'success'}\n")
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
        if pr["base"]["ref"] != os.environ["GITHUB_REF_NAME"]:
            raise ValueError("Dispatch PR verification from its trusted target branch")
        parents = subprocess.check_output(
            ["git", "show", "-s", "--format=%P", "HEAD"], text=True
        ).split()
        if parents != [pr["base"]["sha"], pr["head"]["sha"]]:
            raise ValueError("PR merge changed during checkout; run verification again")
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"tested_head={pr['head']['sha']}\n")
            output.write(f"tested_base={pr['base']['sha']}\n")
        event = {"pull_request": pr}
        name = "pull_request"
    files = changed_files(event, name)
    error = branch_error(event, files or []) or main_promotion_release_error(event)
    if error:
        print(error)
        return 1
    selected = select_jobs(files, event, name, os.environ.get("GITHUB_REF_NAME", ""))
    selected = release_product_checks(
        selected,
        separate_delivery=os.environ.get("CI_SEPARATE_DELIVERY") == "true",
        event_name=name,
        branch=os.environ.get("GITHUB_REF_NAME", ""),
    )
    audit_mode, audit_base = audit_context(
        event, name, os.environ.get("GITHUB_REF_NAME", ""), files
    )
    tested_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    tested_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    print(json.dumps({"files": files, "checks": selected}, indent=2))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"tested_sha={tested_sha}\n")
        output.write(f"tested_tree={tested_tree}\n")
        if event.get("pull_request"):
            output.write(f"tested_base={event['pull_request']['base']['sha']}\n")
            output.write(f"tested_head={event['pull_request']['head']['sha']}\n")
        output.write(f"audit_mode={audit_mode}\n")
        output.write(f"audit_base={audit_base}\n")
        output.write(
            f"deploy={str(should_deploy(files, name, os.environ.get('GITHUB_REF_NAME', ''))).lower()}\n"
        )
        output.write(f"selected={json.dumps(selected)}\n")
        for job, enabled in selected.items():
            output.write(f"{job}={str(enabled).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
