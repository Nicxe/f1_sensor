#!/usr/bin/env python3
"""Create the isolated Python environment used by local dev verification."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".venv-ci"


def main() -> int:
    if sys.version_info < (3, 14):
        print("Python 3.14 or newer is required to match the HA current CI profile.")
        return 1
    subprocess.run([sys.executable, "-m", "venv", str(ENVIRONMENT)], check=True)
    python = ENVIRONMENT / "bin" / "python"
    subprocess.run([python, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run(
        [python, "-m", "pip", "install", "-r", "requirements/ha-current.txt"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [python, "-m", "pip", "install", "-r", "requirements-dev.txt"],
        cwd=ROOT,
        check=True,
    )
    print(f"Local CI environment is ready: {ENVIRONMENT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
