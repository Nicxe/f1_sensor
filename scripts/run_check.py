#!/usr/bin/env python3
"""Execute an individual shared verification group in an already set-up job."""

import argparse
import os
import subprocess
import sys

try:
    from .verification import ROOT, group_commands
except ImportError:
    from verification import ROOT, group_commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "group",
        choices=(
            "lint",
            "backend",
            "blueprints",
            "frontend",
            "translations",
            "documentation",
            "package",
            "automation",
            "audit",
        ),
    )
    parser.add_argument("--audit-mode", default="gate", choices=("gate", "introduced"))
    parser.add_argument("--audit-base", default="")
    args = parser.parse_args()
    commands, extra = group_commands(
        args.group,
        sys.executable,
        audit_mode=args.audit_mode,
        audit_base=args.audit_base,
    )
    environment = {
        **os.environ,
        **extra,
        "CI": "true",
        "F1_BROWSER": "chromium",
        "F1_MAINTENANCE": "",
        "PYTEST_ADDOPTS": "",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "",
    }
    for command in commands:
        print("$ " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
