#!/usr/bin/env python3
"""Retry registry transport failures without hiding security findings."""

from datetime import date
import json
from pathlib import Path
import subprocess
import time

try:
    from .check_npm_audit import AuditUnavailable, evaluate_audit
except ImportError:  # Direct script execution from the checkout.
    from check_npm_audit import AuditUnavailable, evaluate_audit


def run_audit(allowlist: dict, execute=subprocess.run, sleep=time.sleep) -> int:
    for attempt in range(3):
        try:
            result = execute(
                [
                    "npm",
                    "audit",
                    "--json",
                    "--fetch-retries=0",
                    "--fetch-timeout=30000",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if result.returncode not in (0, 1):
                raise AuditUnavailable(f"npm exited with status {result.returncode}")
            failures = evaluate_audit(
                json.loads(result.stdout), allowlist, date.today()
            )
        except (
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            AuditUnavailable,
        ) as err:
            print(f"Audit unavailable (attempt {attempt + 1}/3): {err}", flush=True)
            if attempt < 2:
                sleep(5 * (attempt + 1))
            continue
        if failures:
            print("npm audit policy failed:\n" + "\n".join(failures))
            return 1
        print("npm audit policy passed")
        return 0
    print("npm audit could not be completed; no security conclusion was made")
    return 2


def main() -> int:
    allowlist = json.loads(Path("quality/npm-audit-allowlist.json").read_text())
    return run_audit(allowlist)


if __name__ == "__main__":
    raise SystemExit(main())
