#!/usr/bin/env python3
"""Validate the external data-source register and its review dates."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("register", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    payload = json.loads(args.register.read_text(encoding="utf-8"))
    failures: list[str] = []
    names: set[str] = set()

    for source in payload.get("sources", []):
        name = str(source.get("name", "")).strip()
        if not name or name in names:
            failures.append(f"missing or duplicate source name: {name!r}")
        names.add(name)
        for key in ("url", "terms_url"):
            parsed = urlparse(str(source.get(key, "")))
            if parsed.scheme != "https" or not parsed.netloc:
                failures.append(f"{name}: {key} must be an HTTPS URL")
        if not str(source.get("license_or_terms", "")).strip():
            failures.append(f"{name}: license_or_terms is required")
        try:
            reviewed = date.fromisoformat(source["reviewed_on"])
            review_by = date.fromisoformat(source["review_by"])
            if reviewed > args.today:
                failures.append(f"{name}: reviewed_on is in the future")
            if review_by < args.today:
                failures.append(f"{name}: review expired on {review_by}")
            if review_by <= reviewed:
                failures.append(f"{name}: review_by must be after reviewed_on")
        except (KeyError, TypeError, ValueError):
            failures.append(f"{name}: invalid review dates")

    if not names:
        failures.append("source register is empty")
    if failures:
        print("Data-source review failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"Data-source review passed for {len(names)} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
