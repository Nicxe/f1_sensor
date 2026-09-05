#!/usr/bin/env python3
"""Fail npm audit unless every finding has a current, explicit exception."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path


class AuditUnavailable(ValueError):
    """The registry did not return a complete npm audit report."""


def evaluate_audit(audit: object, allowlist: dict, today: date) -> list[str]:
    """Evaluate only successful, structurally valid audit responses."""
    if (
        not isinstance(audit, dict)
        or "error" in audit
        or audit.get("auditReportVersion") != 2
        or not isinstance(audit.get("vulnerabilities"), dict)
        or not isinstance(audit.get("metadata"), dict)
        or not isinstance(audit.get("metadata", {}).get("vulnerabilities"), dict)
    ):
        raise AuditUnavailable(
            "npm audit could not be completed: invalid or unavailable registry response"
        )
    vulnerabilities = audit["vulnerabilities"]
    if audit["metadata"]["vulnerabilities"].get("total") != len(vulnerabilities):
        raise AuditUnavailable(
            "npm audit could not be completed: inconsistent finding count"
        )
    for package, vulnerability in vulnerabilities.items():
        if (
            not isinstance(vulnerability, dict)
            or not isinstance(vulnerability.get("via"), list)
            or not vulnerability["via"]
        ):
            raise AuditUnavailable(f"invalid advisory data for {package}")
        for item in vulnerability["via"]:
            if isinstance(item, str) and item in vulnerabilities:
                continue
            if isinstance(item, dict) and isinstance(item.get("source"), int):
                continue
            raise AuditUnavailable(f"unresolved advisory data for {package}")
    allowed: dict[tuple[str, int], date] = {}
    failures: list[str] = []

    for entry in allowlist.get("entries", []):
        try:
            expiry = date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"invalid expiry for {entry.get('package', '<unknown>')}")
            continue
        if expiry < today:
            failures.append(f"expired exception for {entry['package']} on {expiry}")
        for advisory in entry.get("advisory_ids", []):
            allowed[(entry["package"], int(advisory))] = expiry

    findings: set[tuple[str, int]] = set()
    for package, vulnerability in vulnerabilities.items():
        advisories = {
            item["source"] for item in vulnerability["via"] if isinstance(item, dict)
        }
        findings.update((package, advisory) for advisory in advisories)

    for finding in sorted(findings):
        if finding not in allowed:
            failures.append(f"{finding[0]}: advisory {finding[1]} is not allowed")
    for exception in sorted(allowed):
        if exception not in findings:
            failures.append(
                f"stale exception {exception[0]} advisory {exception[1]} is no longer present"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument(
        "--allowlist", type=Path, default=Path("quality/npm-audit-allowlist.json")
    )
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    try:
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
        failures = evaluate_audit(audit, allowlist, args.today)
    except (AuditUnavailable, json.JSONDecodeError, OSError) as err:
        print(f"npm audit unavailable: {err}")
        return 2
    if failures:
        print("npm audit policy failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("npm audit policy passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
