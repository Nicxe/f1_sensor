#!/usr/bin/env python3
"""Verify a specific source snapshot with the same check commands as GitHub."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
import shlex
import subprocess
import sys

from ci_environment import (
    PYTHON,
    ROOT,
    dependency_fingerprints,
    environment_errors,
    installed_versions,
    tool_environment,
)
from ci_policy import audit_context, select_jobs
from verification import command_plan as shared_command_plan

REMOTE_ONLY = ("proposed PR merge result", "validation (hassfest and HACS)")


def git_output(args: Sequence[str]) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(
            f"Could not establish Git comparison: {result.stderr.decode().strip()}"
        )
    return result.stdout


def git_paths(args: Sequence[str]) -> set[str]:
    return {path.decode() for path in git_output(args).split(b"\0") if path}


def resolve_base(base: str) -> str:
    return (
        git_output(["rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"])
        .decode()
        .strip()
    )


def changed_files(base: str) -> list[str]:
    """A missing comparison is an error, never evidence of no changes."""
    revision = resolve_base(base)
    merge_base = git_output(["merge-base", revision, "HEAD"]).decode().strip()
    files = git_paths(
        ["diff", "--no-renames", "--name-only", "-z", f"{merge_base}...HEAD"]
    )
    files.update(git_paths(["diff", "--no-renames", "--name-only", "-z"]))
    files.update(git_paths(["diff", "--cached", "--no-renames", "--name-only", "-z"]))
    files.update(git_paths(["ls-files", "--others", "--exclude-standard", "-z"]))
    return sorted(files)


def source_fingerprint() -> str:
    """Bind evidence to file contents, deletions and executable modes, not HEAD alone."""
    paths = git_paths(["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    digest = sha256()
    for name in sorted(paths):
        path = ROOT / name
        digest.update(name.encode() + b"\0")
        if path.is_symlink():
            digest.update(b"link:" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(
                str(path.stat().st_mode & 0o111).encode() + b"\0" + path.read_bytes()
            )
        else:
            digest.update(b"deleted")
        digest.update(b"\0")
    return digest.hexdigest()


def ci_python() -> str:
    return str(PYTHON)


def command_plan(selected: dict[str, bool], *, audit_mode="gate", audit_base=""):
    return shared_command_plan(
        selected, ci_python(), audit_mode=audit_mode, audit_base=audit_base
    )


def display(command: Sequence[str]) -> str:
    return shlex.join(command)


def run(plan, *, print_only: bool) -> int:
    for name, commands, extra_environment in plan:
        print(f"\n==> {name}", flush=True)
        for command in commands:
            print(f"$ {display(command)}", flush=True)
            if print_only:
                continue
            environment = {**tool_environment(), **extra_environment}
            result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
            if result.returncode:
                print(
                    f"{name} failed with exit code {result.returncode}", file=sys.stderr
                )
                return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("changed", "full", "release"))
    parser.add_argument(
        "--target", choices=("dev", "content", "beta", "main"), default="dev"
    )
    parser.add_argument("--base", default=os.environ.get("VERIFY_BASE"))
    parser.add_argument("--print-plan", action="store_true")
    args = parser.parse_args()
    if args.mode == "release" and args.target not in ("beta", "main"):
        parser.error("release verification requires --target beta or --target main")
    base = args.base or f"origin/{args.target}"
    receipt_path = None
    try:
        previous_receipt = ROOT / "test-results/verification.json"
        if not args.print_plan and previous_receipt.is_file():
            receipt_path = previous_receipt
            receipt_path.write_text(
                json.dumps(
                    {
                        "status": "not_verified",
                        "reason": "A new verification attempt has started",
                    }
                )
                + "\n"
            )
        planned_source = source_fingerprint() if not args.print_plan else None
        base_sha = resolve_base(base)
        files = changed_files(base) if args.mode == "changed" else None
        if files == []:
            print(
                "No changes found; no verification was performed. Use verify:dev for the full current snapshot."
            )
            return 3
        event = {"before": base_sha}
        event_name = "push" if args.mode == "changed" else "workflow_dispatch"
        selected = select_jobs(files, event, event_name, args.target)
        audit_mode, audit_base = audit_context(event, event_name, args.target, files)
        plan = command_plan(selected, audit_mode=audit_mode, audit_base=audit_base)
        print(
            f"Verification target: {args.target}; comparison: {base} ({base_sha[:12]})"
        )
        if files is not None:
            print("Changed files:\n" + "\n".join(f"- {path}" for path in files))
        print("Selected checks: " + ", ".join(name for name, _, _ in plan))
        print("Remote confirmation required: " + ", ".join(REMOTE_ONLY))
        if args.print_plan:
            return run(plan, print_only=True)
        if not plan:
            print("No executable checks apply; no verification receipt was created.")
            return 3
        receipt_path = ROOT / "test-results/verification.json"
        receipt_path.parent.mkdir(exist_ok=True)
        receipt_path.write_text(
            json.dumps({"status": "running", "source": planned_source}) + "\n"
        )
        errors = environment_errors()
        if errors:
            print("Refreshing isolated CI setup:\n" + "\n".join(errors), flush=True)
            result = subprocess.run(
                [sys.executable, "scripts/setup_ci_environment.py"],
                cwd=ROOT,
                check=False,
            )
            if result.returncode:
                return result.returncode
            errors = environment_errors()
            if errors:
                raise ValueError("\n".join(errors))
        before = source_fingerprint()
        if before != planned_source:
            raise ValueError(
                "Source files changed after check selection; rerun verification"
            )
        versions_before = installed_versions()
        dependencies_before = dependency_fingerprints()
        result = run(plan, print_only=False)
        if result:
            receipt_path.write_text(
                json.dumps({"status": "failed", "source": before}) + "\n"
            )
            return result
        if source_fingerprint() != before:
            raise ValueError(
                "Source files changed during verification; rerun the affected checks"
            )
        if (
            installed_versions() != versions_before
            or dependency_fingerprints() != dependencies_before
        ):
            raise ValueError(
                "Installed tools or dependencies changed during verification; rerun the checks"
            )
        receipt = {
            "status": "local_passed_remote_pending",
            "completed_at": datetime.now(UTC).isoformat(),
            "source": before,
            "target": args.target,
            "profile": args.mode,
            "base": base_sha,
            "checks": [name for name, _, _ in plan],
            "versions": versions_before,
            "dependencies": dependencies_before,
            "remote_confirmation": list(REMOTE_ONLY),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"\nLocal verification passed for source {before[:12]}. GitHub confirmation remains pending."
        )
        print(f"Evidence: {receipt_path}")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        if receipt_path is not None:
            receipt_path.write_text(
                json.dumps({"status": "failed", "error": str(error)}) + "\n"
            )
        print(f"Verification could not be completed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
