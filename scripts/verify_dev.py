#!/usr/bin/env python3
"""Run the locally reproducible subset of the dev GitHub Actions checks."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import subprocess
import sys

from ci_policy import select_jobs

ROOT = Path(__file__).resolve().parents[1]
RUFF_PATHS = ("custom_components", "scripts", "ci_tests", "ci_smoke")
REMOTE_ONLY = ("validation (hassfest and HACS)",)


def git_paths(args: Sequence[str]) -> set[str]:
    """Return NUL-delimited paths from a Git command, or no paths on failure."""
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        return set()
    return {path.decode() for path in result.stdout.split(b"\0") if path}


def changed_files(base: str) -> list[str]:
    """Include committed, staged, unstaged, and untracked local changes."""
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    files: set[str] = set()
    if merge_base.returncode == 0:
        files.update(
            git_paths(
                [
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    f"{merge_base.stdout.strip()}...HEAD",
                ]
            )
        )
    files.update(git_paths(["diff", "--no-renames", "--name-only", "-z"]))
    files.update(git_paths(["diff", "--cached", "--no-renames", "--name-only", "-z"]))
    files.update(git_paths(["ls-files", "--others", "--exclude-standard", "-z"]))
    return sorted(files)


def ci_python() -> str:
    """Prefer the isolated CI environment when it has been set up."""
    configured = os.environ.get("F1_CI_PYTHON")
    if configured:
        return configured
    virtualenv_python = ROOT / ".venv-ci" / "bin" / "python"
    return str(virtualenv_python) if virtualenv_python.is_file() else sys.executable


def command_plan(
    selected: dict[str, bool],
) -> list[tuple[str, list[list[str]], dict[str, str]]]:
    """Map the CI selection to checks that can run faithfully on a developer Mac."""
    python = ci_python()
    plan: list[tuple[str, list[list[str]], dict[str, str]]] = []
    if selected["lint"]:
        plan.append(
            (
                "lint",
                [
                    [python, "-m", "ruff", "check", *RUFF_PATHS],
                    [python, "-m", "ruff", "format", "--check", *RUFF_PATHS],
                ],
                {},
            )
        )
    if selected["backend"]:
        plan.append(
            (
                "backend",
                [
                    [python, "scripts/run_ci_tests.py"],
                    [python, "scripts/test_installed_release.py"],
                ],
                {"TEST_PROFILE": "current", "BLUEPRINTS_ONLY": "false"},
            )
        )
    elif selected["blueprints"]:
        plan.append(
            (
                "blueprints",
                [[python, "scripts/run_ci_tests.py"]],
                {"TEST_PROFILE": "current", "BLUEPRINTS_ONLY": "true"},
            )
        )
    if selected["frontend"]:
        plan.append(
            (
                "frontend",
                [
                    ["npm", "run", "test:frontend:unit"],
                    ["npm", "run", "test:frontend"],
                ],
                {},
            )
        )
    if selected["documentation"]:
        plan.append(("documentation", [["npm", "run", "test:docs"]], {}))
    if selected["package"]:
        plan.append(
            (
                "package",
                [
                    [
                        python,
                        "scripts/check_translations.py",
                        "custom_components/f1_sensor/translations",
                    ],
                    [python, "scripts/check_release_build.py"],
                ],
                {},
            )
        )
    if selected["automation"]:
        plan.append(("automation", [["npm", "run", "test:automation"]], {}))
    return plan


def display(command: Sequence[str]) -> str:
    return " ".join(shlex_quote(part) for part in command)


def shlex_quote(value: str) -> str:
    """Use shell-safe output without invoking a shell for verification."""
    safe = value.replace("_", "").replace("-", "").replace("/", "").replace(".", "")
    return value if safe.isalnum() else repr(value)


def run(
    plan: list[tuple[str, list[list[str]], dict[str, str]]], *, print_only: bool
) -> int:
    for name, commands, extra_environment in plan:
        print(f"\n==> {name}", flush=True)
        for command in commands:
            print(f"$ {display(command)}", flush=True)
            if print_only:
                continue
            environment = {**os.environ, **extra_environment}
            result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
            if result.returncode:
                print(
                    f"{name} failed with exit code {result.returncode}", file=sys.stderr
                )
                return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("changed", "full"))
    parser.add_argument(
        "--base",
        default=os.environ.get("VERIFY_BASE", "origin/dev"),
        help="Git ref used by changed mode (default: origin/dev)",
    )
    parser.add_argument("--print-plan", action="store_true")
    args = parser.parse_args()

    if args.mode == "changed":
        files = changed_files(args.base)
        if not files:
            print("No local changes to verify.")
            return 0
        selected = select_jobs(files, {}, "push", "dev")
        print("Changed files:\n" + "\n".join(f"- {path}" for path in files))
    else:
        files = None
        selected = select_jobs(None, {}, "workflow_dispatch", "dev")

    selected["audit"] = False
    plan = command_plan(selected)
    print("\nSelected local checks: " + ", ".join(name for name, _, _ in plan))
    if selected["validation"]:
        print("Remote-only CI checks: " + ", ".join(REMOTE_ONLY))
    if args.mode == "full" and files is None:
        print("The dependency audit is intentionally not part of dev-push CI.")
    return run(plan, print_only=args.print_plan)


if __name__ == "__main__":
    raise SystemExit(main())
