#!/usr/bin/env python3
"""Validate the expiring F1TV Token Helper security review record."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    payload = json.loads(args.review.read_text(encoding="utf-8"))
    failures: list[str] = []

    try:
        reviewed = date.fromisoformat(payload["reviewed_on"])
        review_by = date.fromisoformat(payload["review_by"])
        if reviewed > args.today:
            failures.append("reviewed_on is in the future")
        if review_by < args.today:
            failures.append(f"review expired on {review_by}")
        if review_by <= reviewed:
            failures.append("review_by must be after reviewed_on")
    except (KeyError, TypeError, ValueError):
        failures.append("invalid review dates")

    repository = urlparse(str(payload.get("source_repository", "")))
    if repository.scheme != "https" or repository.netloc != "github.com":
        failures.append("source_repository must be an HTTPS GitHub URL")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("reviewed_commit", ""))):
        failures.append("reviewed_commit must be a full Git commit SHA")
    if not re.fullmatch(
        r"[0-9a-f]{64}", str(payload.get("reproducible_build_sha256", ""))
    ):
        failures.append("reproducible_build_sha256 must be a SHA-256 digest")
    if payload.get("manifest_version") != 3:
        failures.append("Manifest V3 is required")
    if payload.get("production_dependency_vulnerabilities") != 0:
        failures.append("production dependency vulnerabilities must be zero")
    if payload.get("review_result") != "approved":
        failures.append("review_result must be approved")

    required_permissions = {"cookies", "activeTab", "scripting", "storage"}
    if not required_permissions.issubset(set(payload.get("permissions", []))):
        failures.append("required reviewed permissions are missing")
    required_privacy = {
        "analytics": False,
        "remote_code": False,
        "project_backend": False,
        "persistent_token_storage": False,
        "send_requires_user_action": True,
        "pairing_session_uses_session_storage": True,
    }
    privacy = payload.get("privacy", {})
    for key, expected in required_privacy.items():
        if privacy.get(key) is not expected:
            failures.append(f"privacy.{key} must be {expected}")
    callback_policy = payload.get("callback_policy", {})
    for key in (
        "https_required_for_public_hosts",
        "local_http_allowed",
        "exact_callback_path_required",
        "userinfo_query_and_fragment_rejected",
    ):
        if callback_policy.get(key) is not True:
            failures.append(f"callback_policy.{key} must be true")

    if failures:
        print("Token Helper review failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(
        "Token Helper review passed for "
        f"{payload['extension_version']} at {payload['reviewed_commit'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
