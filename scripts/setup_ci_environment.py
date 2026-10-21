#!/usr/bin/env python3
"""Create the isolated Python environment used by local dev verification."""

from __future__ import annotations

import json
import os
import subprocess
import sys

try:
    from .ci_environment import (
        PYTHON,
        ROOT,
        STAMP,
        TOOLS,
        dependency_fingerprints,
        expected_versions,
        installed_versions,
        tool_environment,
    )
    from .setup_actionlint import install as install_actionlint
    from .setup_node import install as install_node
except ImportError:
    from ci_environment import (
        PYTHON,
        ROOT,
        STAMP,
        TOOLS,
        dependency_fingerprints,
        expected_versions,
        installed_versions,
        tool_environment,
    )
    from setup_actionlint import install as install_actionlint
    from setup_node import install as install_node


def main() -> int:
    versions = expected_versions()
    if f"{sys.version_info.major}.{sys.version_info.minor}" != versions["python"]:
        print(
            f"Python {versions['python']} is required to match the HA current CI profile."
        )
        return 1
    subprocess.run(
        [
            getattr(sys, "_base_executable", sys.executable),
            "-m",
            "venv",
            "--clear",
            str(PYTHON.parent.parent),
        ],
        check=True,
    )
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-r", "requirements/ha-current.txt"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-r", "requirements-dev.txt"],
        cwd=ROOT,
        check=True,
    )
    runtime = install_node()
    subprocess.run(
        [
            str(runtime / "bin/node"),
            str(runtime / "lib/node_modules/npm/bin/npm-cli.js"),
            "install",
            "--prefix",
            str(TOOLS),
            "--no-save",
            "--package-lock=false",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            f"npm@{versions['npm']}",
        ],
        cwd=ROOT,
        check=True,
        env=os.environ,
    )
    environment = tool_environment()
    if installed_versions() != versions:
        raise RuntimeError(
            "The isolated tool versions do not match the checked-in pins"
        )
    subprocess.run(
        ["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT, env=environment, check=True
    )
    subprocess.run(
        ["npm", "exec", "--", "playwright", "install", "chromium"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    install_actionlint()
    STAMP.write_text(
        json.dumps(
            {"versions": versions, "dependencies": dependency_fingerprints()}, indent=2
        )
        + "\n"
    )
    print(f"Local CI environment is ready: {PYTHON.parent.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
