#!/usr/bin/env python3
"""Prove release determinism and reject non-runtime content."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

from verify_release import verify_release

FORBIDDEN = {
    "AGENTS.md",
    "debugging_tyres.md",
    "track_map_static_geometry_builder.py",
    "track_map_static_geometry_calibrator.py",
    "track_map_static_geometry_maintenance.py",
    "track_map_static_geometry_qa.py",
}


def _build(output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/build_release.py",
            "--component",
            "custom_components/f1_sensor",
            "--output",
            str(output),
            "--version",
            "0.0.0-phase5",
        ],
        check=True,
    )


def main() -> int:
    with TemporaryDirectory(prefix="f1-sensor-release-") as directory:
        root = Path(directory)
        first = root / "first.zip"
        second = root / "second.zip"
        _build(first)
        _build(second)
        verify_release(first, "0.0.0-phase5")
        verify_release(second, "0.0.0-phase5")
        first_hash = hashlib.sha256(first.read_bytes()).digest()
        second_hash = hashlib.sha256(second.read_bytes()).digest()
        if first_hash != second_hash:
            raise ValueError("release build is not deterministic")
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
            if "manifest.json" not in names or any(
                name.startswith("f1_sensor/") for name in names
            ):
                raise ValueError(
                    "release must preserve the published flat component layout"
                )
            if any(
                name.startswith(("tests/", "__pycache__/"))
                or "/tests/" in name
                or "/__pycache__/" in name
                for name in names
            ):
                raise ValueError("release contains tests or bytecode")
            shipped_names = {Path(name).name for name in names}
            leaked = FORBIDDEN & shipped_names
            if leaked:
                raise ValueError(f"release contains excluded files: {sorted(leaked)}")
            manifest = archive.read("manifest.json").decode()
            if '"version": "0.0.0-phase5"' not in manifest:
                raise ValueError("release manifest version was not updated")
            for name in names:
                if name.endswith(".py"):
                    compile(archive.read(name), name, "exec")
        for suffix in (".sha256", ".spdx.json"):
            if not first.with_suffix(first.suffix + suffix).is_file():
                raise ValueError(f"release evidence missing: {suffix}")
    print("Release artifact is deterministic and contains runtime files only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
