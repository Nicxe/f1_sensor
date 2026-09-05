#!/usr/bin/env python3
"""Run HA against an extracted release, never against the source checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile


def main() -> int:
    repository = Path.cwd()
    with TemporaryDirectory(prefix="f1-installed-") as directory:
        root = Path(directory)
        archive = root / "f1_sensor.zip"
        subprocess.run(
            [
                sys.executable,
                "scripts/build_release.py",
                "--component",
                "custom_components/f1_sensor",
                "--output",
                str(archive),
                "--version",
                "0.0.0-ci",
            ],
            check=True,
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
