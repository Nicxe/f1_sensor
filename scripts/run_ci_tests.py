#!/usr/bin/env python3
"""Run reproducible Python profiles in a checkout, without external HA paths."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path("custom_components/f1_sensor/tests")
MINIMUM = (
    "test_setup.py",
    "test_config_flow_entity_naming.py",
    "test_config_flow_behavior_matrix.py",
    "test_storage.py",
    "test_helpers.py",
    "test_coordinator.py",
    "test_device_trigger.py",
    "test_diagnostics.py",
    "test_frontend.py",
    "test_session_clock.py",
    "test_auth.py",
    "test_auth_http.py",
    "test_weather.py",
    "test_track_map_websocket.py",
)


def main() -> int:
    if not shutil.which("node"):
        raise RuntimeError(
            "Node.js is required; frontend regression probes must not be skipped"
        )
    profile = os.environ.get("TEST_PROFILE", "current")
    blueprint = os.environ.get("BLUEPRINTS_ONLY") == "true"
    if blueprint:
        paths = sorted(ROOT.glob("test_*blueprint.py"))
        if not paths:
            raise ValueError("no blueprint tests were found")
    elif profile == "minimum":
        paths = [ROOT / name for name in MINIMUM if (ROOT / name).is_file()]
    else:
        paths = [ROOT]
    Path("test-results").mkdir(exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        *map(str, paths),
        "-q",
        "--durations=10",
        "--strict-markers",
        "-m",
        "not performance",
        f"--junitxml=test-results/python-{profile}.xml",
    ]
    coverage = profile == "current" and not blueprint
    if coverage:
        command += [
            "--cov=custom_components.f1_sensor",
            "--cov-report=term-missing",
            "--cov-report=json:coverage.json",
        ]
    result = subprocess.run(command, check=False).returncode
    if result == 0 and coverage:
        result = subprocess.run(
            [sys.executable, "scripts/check_coverage.py", "coverage.json"], check=False
        ).returncode
    return result


if __name__ == "__main__":
    raise SystemExit(main())
