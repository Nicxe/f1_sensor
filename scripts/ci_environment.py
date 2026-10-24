"""Versioned, isolated tools and dependency fingerprints for local preflight."""

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

try:
    from .setup_node import runtime_directory
except ImportError:
    from setup_node import runtime_directory

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools-ci"
STAMP = TOOLS / "environment.json"
PYTHON = ROOT / ".venv-ci/bin/python"
REQUIREMENTS = ("requirements/ha-current.txt", "requirements-dev.txt")
NPM_INPUTS = ("package.json", "package-lock.json", ".node-version")


def digest_files(paths: tuple[str, ...]) -> str:
    digest = sha256()
    for name in paths:
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return digest.hexdigest()


def npm_install_inputs() -> tuple[str, ...]:
    """Include postinstall patches and npm configuration, not just the lock."""
    patches = tuple(
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "patches").rglob("*"))
        if path.is_file()
    )
    configuration = (".npmrc",) if (ROOT / ".npmrc").is_file() else ()
    return (*NPM_INPUTS, *configuration, *patches)


def tool_environment() -> dict[str, str]:
    """Use private binaries without changing the user's global installation."""
    return {
        **os.environ,
        "PATH": os.pathsep.join(
            (
                str(PYTHON.parent),
                str(TOOLS / "node_modules/.bin"),
                str(runtime_directory() / "bin"),
                os.environ["PATH"],
            )
        ),
        "CI": "true",
        "F1_BROWSER": "chromium",
        "F1_MAINTENANCE": "",
        "F1_VISUAL_REVIEW": "",
        "PYTEST_ADDOPTS": "",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "",
    }


def output(command: list[str], *, environment=None) -> str:
    return subprocess.check_output(
        command, cwd=ROOT, env=environment, text=True, stderr=subprocess.PIPE
    ).strip()


def expected_versions() -> dict[str, str]:
    package = json.loads((ROOT / "package.json").read_text())
    return {
        "node": "v" + (ROOT / ".node-version").read_text().strip(),
        "npm": package["packageManager"].removeprefix("npm@"),
        "python": (ROOT / ".python-version").read_text().strip(),
    }


def installed_versions() -> dict[str, str]:
    env = tool_environment()
    return {
        "node": output(["node", "--version"], environment=env),
        "npm": output(["npm", "--version"], environment=env),
        "python": output(
            [
                str(PYTHON),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ]
        ),
    }


def dependency_fingerprints() -> dict[str, str]:
    """Record installed metadata as well as the inputs used to install it."""
    return {
        "setup": digest_files(
            (
                "scripts/setup_ci_environment.py",
                "scripts/setup_node.py",
                "scripts/setup_actionlint.py",
                "scripts/ci_environment.py",
            )
        ),
        "requirements": digest_files((*REQUIREMENTS, ".python-version")),
        "npm_inputs": digest_files(npm_install_inputs()),
        "python_packages": sha256(
            output([str(PYTHON), "-m", "pip", "freeze", "--all"]).encode()
        ).hexdigest(),
        "npm_packages": sha256(
            (ROOT / "node_modules/.package-lock.json").read_bytes()
        ).hexdigest(),
    }


def environment_errors() -> list[str]:
    try:
        recorded = json.loads(STAMP.read_text())
        errors = []
        versions = installed_versions()
        for tool, expected in expected_versions().items():
            if versions[tool] != expected:
                errors.append(f"{tool}: expected {expected}, found {versions[tool]}")
        if dependency_fingerprints() != recorded.get("dependencies"):
            errors.append("Installed dependencies no longer match the verified setup")
        if not (TOOLS / "bin/actionlint").is_file():
            errors.append("The pinned workflow validator is missing")
        browser = output(
            [
                "node",
                "-e",
                "process.stdout.write(require('playwright').chromium.executablePath())",
            ],
            environment=tool_environment(),
        )
        if not Path(browser).is_file():
            errors.append("The locked Playwright Chromium browser is missing")
        return errors
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        return [f"The isolated CI environment needs setup: {error}"]
