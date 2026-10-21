#!/usr/bin/env python3
"""Evaluate actionable npm findings with narrow, expiring exceptions."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

SEVERITIES = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
DEFAULT_POLICY = {
    "version": 1,
    "blocking_severities": ["high", "critical"],
    "exception_warning_days": 14,
}


class AuditUnavailable(ValueError):
    """The registry did not return a complete npm audit report."""


def audit_findings(audit: object) -> dict[tuple[str, int], dict]:
    """Validate a registry report and retain advisory and dependency-path identity."""
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
    total = audit["metadata"]["vulnerabilities"].get("total")
    if type(total) is not int or total != len(vulnerabilities):
        raise AuditUnavailable(
            "npm audit could not be completed: inconsistent finding count"
        )
    for package, vulnerability in vulnerabilities.items():
        if (
            not isinstance(vulnerability, dict)
            or not isinstance(vulnerability.get("severity"), str)
            or vulnerability["severity"] not in SEVERITIES
            or not isinstance(vulnerability.get("via"), list)
            or not vulnerability["via"]
            or not isinstance(vulnerability.get("nodes"), list)
            or not vulnerability["nodes"]
            or not all(
                isinstance(node, str) and node for node in vulnerability["nodes"]
            )
        ):
            raise AuditUnavailable(f"invalid advisory data for {package}")
        for item in vulnerability["via"]:
            if isinstance(item, str) and item in vulnerabilities:
                continue
            if (
                isinstance(item, dict)
                and type(item.get("source")) is int
                and item["source"] > 0
                and isinstance(item.get("severity", vulnerability["severity"]), str)
                and item.get("severity", vulnerability["severity"]) in SEVERITIES
            ):
                continue
            raise AuditUnavailable(f"unresolved advisory data for {package}")

    def resolves(package: str, seen: set[str]) -> bool:
        if package in seen:
            return False
        return any(
            isinstance(item, dict) or resolves(item, seen | {package})
            for item in vulnerabilities[package]["via"]
        )

    if any(not resolves(package, set()) for package in vulnerabilities):
        raise AuditUnavailable("npm audit returned an unresolved advisory cycle")

    findings: dict[tuple[str, int], dict] = {}
    for package, vulnerability in vulnerabilities.items():
        for advisory in vulnerability["via"]:
            if not isinstance(advisory, dict):
                continue
            identity = (package, advisory["source"])
            severity = advisory.get("severity", vulnerability["severity"])
            previous_severity = findings.get(identity, {}).get("severity", "info")
            findings[identity] = {
                "severity": max((severity, previous_severity), key=SEVERITIES.get),
                "nodes": set(vulnerability["nodes"]),
            }
    if vulnerabilities and not findings:
        raise AuditUnavailable("npm audit returned no resolvable advisories")
    return findings


def validate_policy(policy: dict) -> None:
    """Reject an ambiguous or accidentally weakened configuration."""
    if not isinstance(policy, dict):
        raise ValueError("invalid npm audit policy")
    severities = policy.get("blocking_severities")
    days = policy.get("exception_warning_days")
    if (
        policy.get("version") != 1
        or not isinstance(severities, list)
        or not all(isinstance(severity, str) for severity in severities)
        or not {"high", "critical"}.issubset(severities)
        or any(severity not in SEVERITIES for severity in severities)
        or type(days) is not int
        or days < 1
    ):
        raise ValueError("invalid npm audit policy")


def evaluate_audit(
    audit: object,
    allowlist: dict,
    today: date,
    *,
    policy: dict | None = None,
    baseline: object | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    """Block applicable severe findings; a baseline limits gating to introduced paths.

    Every scope, including build and development tooling, is evaluated. A fixed
    dependency must not remain blocked by an old exception's expiry date.
    """
    policy = DEFAULT_POLICY if policy is None else policy
    validate_policy(policy)
    warnings = [] if warnings is None else warnings
    findings = audit_findings(audit)
    previous = {} if baseline is None else audit_findings(baseline)
    allowed: dict[tuple[str, int], date] = {}
    allowed_nodes: dict[tuple[str, int], set[str]] = {}
    failures: list[str] = []

    entries = allowlist.get("entries") if isinstance(allowlist, dict) else None
    if not isinstance(entries, list):
        return ["invalid npm audit exception list"]
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("package"), str)
            or not entry["package"]
            or not isinstance(entry.get("advisory_ids"), list)
            or not entry["advisory_ids"]
            or not all(type(item) is int and item > 0 for item in entry["advisory_ids"])
        ):
            failures.append("invalid npm audit exception identity")
            continue
        try:
            expiry = date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"invalid expiry for {entry.get('package', '<unknown>')}")
            continue
        active = any(
            (entry["package"], item) in findings for item in entry["advisory_ids"]
        )
        remaining = (expiry - today).days
        if not active and remaining < 0:
            warnings.append(
                f"unused expired exception for {entry['package']}: remove it"
            )
        elif 0 <= remaining <= policy["exception_warning_days"]:
            warnings.append(
                f"exception for {entry['package']} expires on {expiry} "
                f"in {remaining} day(s){'' if active else ' (currently unused)'}"
            )
        nodes = entry.get("allowed_nodes")
        if nodes is not None and (
            not isinstance(nodes, list)
            or not nodes
            or not all(isinstance(node, str) and node for node in nodes)
        ):
            failures.append(f"invalid allowed nodes for {entry['package']}")
            continue
        for advisory in entry.get("advisory_ids", []):
            finding = (entry["package"], advisory)
            if finding in allowed:
                failures.append(
                    f"duplicate exception for {finding[0]} advisory {finding[1]}"
                )
            allowed[finding] = expiry
            if nodes is not None:
                allowed_nodes[finding] = set(nodes)

    for finding, detail in sorted(findings.items()):
        severity = detail["severity"]
        old = previous.get(finding, {})
        old_nodes = old.get("nodes", set())
        if (
            severity in policy["blocking_severities"]
            and old.get("severity") not in policy["blocking_severities"]
        ):
            old_nodes = set()
        nodes = detail["nodes"] - old_nodes
        label = f"{finding[0]}: {severity} advisory {finding[1]}"
        if not nodes:
            warnings.append(f"existing {label}; no new vulnerable dependency path")
            continue
        if severity not in policy["blocking_severities"]:
            warnings.append(f"{label} requires review (below the blocking severity)")
            continue
        if finding not in allowed:
            failures.append(f"{label} is not allowed ({', '.join(sorted(nodes))})")
        elif allowed[finding] < today:
            failures.append(f"expired exception for {finding[0]} on {allowed[finding]}")
        elif finding in allowed_nodes and not nodes.issubset(allowed_nodes[finding]):
            failures.append(f"{label} is outside allowed nodes")
        else:
            warnings.append(f"accepted {label} until {allowed[finding]}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument(
        "--allowlist", type=Path, default=Path("quality/npm-audit-allowlist.json")
    )
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--policy", type=Path, default=Path("quality/npm-audit-policy.json")
    )
    args = parser.parse_args()
    try:
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        warnings: list[str] = []
        failures = evaluate_audit(
            audit, allowlist, args.today, policy=policy, warnings=warnings
        )
    except (ValueError, OSError) as err:
        print(f"npm audit unavailable: {err}")
        return 2
    for warning in warnings:
        print(f"npm audit warning: {warning}")
    if failures:
        print("npm audit policy failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("npm audit policy passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
