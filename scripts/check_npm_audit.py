#!/usr/bin/env python3
"""Fail npm audit unless every finding has a current, explicit exception."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path


def _advisories(vulnerability: dict[str, object]) -> set[int]:
    return {
        int(item["source"])
        for item in vulnerability.get("via", [])
        if isinstance(item, dict) and isinstance(item.get("source"), int)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("quality/npm-audit-allowlist.json"),
    )
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
    allowed: dict[tuple[str, int], date] = {}
    failures: list[str] = []

    for entry in allowlist.get("entries", []):
        try:
            expiry = date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"invalid expiry for {entry.get('package', '<unknown>')}")
            continue
        if expiry < args.today:
            failures.append(f"expired exception for {entry['package']} on {expiry}")
        for advisory in entry.get("advisory_ids", []):
            allowed[(entry["package"], int(advisory))] = expiry

    findings: set[tuple[str, int]] = set()
    for package, vulnerability in audit.get("vulnerabilities", {}).items():
        advisories = _advisories(vulnerability)
        findings.update((package, advisory) for advisory in advisories)

    for finding in sorted(findings):
        if finding not in allowed:
            failures.append(f"{finding[0]}: advisory {finding[1]} is not allowed")
    for exception in sorted(allowed):
        if exception not in findings:
            failures.append(
                f"stale exception {exception[0]} advisory {exception[1]} is no longer present"
            )

    if failures:
        print("npm audit policy failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"npm audit policy passed with {len(findings)} reviewed advisory finding(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
