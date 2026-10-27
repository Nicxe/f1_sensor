#!/usr/bin/env python3
"""Share deterministic dependency risk checks between local and GitHub CI."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

try:
    from .check_npm_audit import (
        AuditUnavailable,
        evaluate_audit,
        match_advisory_versions,
        project_npm_cli,
        validate_report,
    )
except ImportError:  # Direct script execution from the checkout.
    from check_npm_audit import (
        AuditUnavailable,
        evaluate_audit,
        match_advisory_versions,
        project_npm_cli,
        validate_report,
    )


def read_baseline(base: str, execute=subprocess.run) -> dict[str, str]:
    """Read a fixed commit's npm inputs without checking out or installing its code."""
    revision = execute(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", revision):
        raise ValueError("the audit baseline did not resolve to a commit")
    return {
        name: execute(
            ["git", "show", f"{revision}:{name}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for name in ("package.json", "package-lock.json")
    }


def registry_report(
    execute, sleep, directory: str | None = None, *, npm_cli: Path
) -> dict:
    """Require a complete report after bounded transport retries, never an install."""
    for attempt in range(3):
        try:
            command = [
                "node",
                str(npm_cli),
                "audit",
                "--json",
                "--package-lock-only",
                "--ignore-scripts",
                "--fetch-retries=0",
                "--fetch-timeout=30000",
            ]
            if directory is not None:
                command.extend(["--prefix", directory])
            result = execute(
                command,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if result.returncode not in (0, 1):
                raise AuditUnavailable(f"npm exited with status {result.returncode}")
            report = json.loads(result.stdout)
            validate_report(report)
            return report
        except (
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            AuditUnavailable,
            OSError,
        ) as err:
            print(f"Audit unavailable (attempt {attempt + 1}/3): {err}", flush=True)
            if attempt < 2:
                sleep(5 * (attempt + 1))
    raise AuditUnavailable("no complete registry report after three attempts")


def run_audit(
    allowlist: dict,
    execute=subprocess.run,
    sleep=time.sleep,
    *,
    policy: dict | None = None,
    mode: str = "gate",
    base: str | None = None,
    target_ref: str | None = None,
    read_base=read_baseline,
    read_lock=lambda: json.loads(Path("package-lock.json").read_text(encoding="utf-8")),
) -> int:
    """Gate full release health or only severe advisory paths introduced since base."""
    try:
        if mode not in ("gate", "introduced") or (mode == "introduced" and not base):
            raise ValueError(
                "introduced mode requires --base with the tested base commit"
            )
        baseline = None
        baseline_lock = None
        npm_cli = project_npm_cli()
        if mode == "introduced":
            files = read_base(base)
            baseline_lock = json.loads(files["package-lock.json"])
            with tempfile.TemporaryDirectory(prefix="f1-audit-base-") as directory:
                for name in ("package.json", "package-lock.json"):
                    Path(directory, name).write_text(files[name], encoding="utf-8")
                baseline = registry_report(execute, sleep, directory, npm_cli=npm_cli)
        if target_ref:
            # A trusted current evaluator can scan an older branch without
            # checking it out, installing its dependencies or executing its code.
            files = read_base(target_ref)
            lock = json.loads(files["package-lock.json"])
            with tempfile.TemporaryDirectory(prefix="f1-audit-target-") as directory:
                for name in ("package.json", "package-lock.json"):
                    Path(directory, name).write_text(files[name], encoding="utf-8")
                report = registry_report(execute, sleep, directory, npm_cli=npm_cli)
        else:
            lock = read_lock()
            report = registry_report(execute, sleep, npm_cli=npm_cli)
        warnings: list[str] = []
        failures = evaluate_audit(
            report,
            allowlist,
            date.today(),
            policy=policy,
            baseline=baseline,
            lock=lock,
            baseline_lock=baseline_lock,
            match_versions=lambda records: match_advisory_versions(
                records, npm_cli=npm_cli
            ),
            warnings=warnings,
        )
    except (ValueError, OSError, subprocess.CalledProcessError) as err:
        print(
            f"npm audit could not be completed; no security conclusion was made: {err}"
        )
        return 2
    for warning in warnings:
        escaped = warning.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning title=Dependency audit::{escaped}")
    if failures:
        print(f"npm audit {mode} policy failed:\n" + "\n".join(failures))
        return 1
    print(
        f"npm audit {mode} policy passed"
        + (f" against {base}" if baseline is not None else "")
        + (f" for {target_ref}" if target_ref else "")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("gate", "introduced"), default="gate")
    parser.add_argument("--base")
    parser.add_argument(
        "--target-ref", help="Audit only npm inputs from this Git ref, never its code"
    )
    parser.add_argument(
        "--allowlist", type=Path, default=Path("quality/npm-audit-allowlist.json")
    )
    parser.add_argument(
        "--policy", type=Path, default=Path("quality/npm-audit-policy.json")
    )
    args = parser.parse_args()
    try:
        allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
    except (ValueError, OSError) as err:
        print(f"npm audit configuration unavailable: {err}")
        return 2
    return run_audit(
        allowlist,
        policy=policy,
        mode=args.mode,
        base=args.base,
        target_ref=args.target_ref,
    )


if __name__ == "__main__":
    raise SystemExit(main())
