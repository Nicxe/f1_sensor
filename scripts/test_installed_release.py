#!/usr/bin/env python3
"""Run HA against an extracted release, never against the source checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

try:
    from .verify_release import verify_release
except ImportError:  # Direct invocation from the checkout.
    from verify_release import verify_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        help="Existing ZIP with adjacent SHA-256/SPDX evidence; never rebuilt",
    )
    parser.add_argument(
        "--version",
        help="Expected release version; defaults to the supplied archive's version",
    )
    args = parser.parse_args()
    repository = Path.cwd()
    with TemporaryDirectory(prefix="f1-installed-") as directory:
        root = Path(directory)
        if args.archive is not None:
            archive = args.archive.resolve()
            with zipfile.ZipFile(archive) as package:
                version = (
                    args.version or json.loads(package.read("manifest.json"))["version"]
                )
        else:
            archive = root / "f1_sensor.zip"
            version = args.version or "0.0.0-ci"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/build_release.py",
                    "--component",
                    "custom_components/f1_sensor",
                    "--output",
                    str(archive),
                    "--version",
                    version,
                ],
                check=True,
            )
        verify_release(archive, version)
        print(
            f"Testing verified archive {archive} (version {version}, "
            f"SHA-256 {hashlib.sha256(archive.read_bytes()).hexdigest()})",
            flush=True,
        )
        component = root / "custom_components/f1_sensor"
        component.mkdir(parents=True)
        (root / "custom_components/__init__.py").touch()
        with zipfile.ZipFile(archive) as package:
            package.extractall(component)
        shutil.copytree(repository / "ci_smoke", root / "tests")
        (root / "conftest.py").write_text(
            "import sys, types\nfrom pathlib import Path\n"
            'namespace = types.ModuleType("custom_components")\n'
            'namespace.__path__ = [str(Path(__file__).parent / "custom_components")]\n'
            'sys.modules["custom_components"] = namespace\n'
            'pytest_plugins = "pytest_homeassistant_custom_component"\n'
        )
        (root / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")
        environment = {
            **os.environ,
            "PYTHONPATH": str(root),
            "F1_INSTALLED_ROOT": str(component),
        }
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=root,
            env=environment,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
