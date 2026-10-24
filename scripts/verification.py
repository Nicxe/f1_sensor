"""Shared check commands for local preflight and GitHub Actions wrappers."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUFF_PATHS = ("conftest.py", "custom_components", "scripts", "ci_tests", "ci_smoke")


def group_commands(
    group: str,
    python: str = sys.executable,
    *,
    audit_mode: str = "gate",
    audit_base: str = "",
) -> tuple[list[list[str]], dict[str, str]]:
    """Keep commands in one place; workflows only provision their environment."""
    audit = [python, "scripts/run_npm_audit.py", "--mode", audit_mode]
    if audit_base:
        audit += ["--base", audit_base]
    groups = {
        "lint": (
            [
                [python, "-m", "ruff", "check", *RUFF_PATHS],
                [python, "-m", "ruff", "format", "--check", *RUFF_PATHS],
            ],
            {},
        ),
        "backend": (
            [
                [python, "scripts/run_ci_tests.py"],
                [python, "scripts/test_installed_release.py"],
            ],
            {"TEST_PROFILE": "current", "BLUEPRINTS_ONLY": "false"},
        ),
        "blueprints": (
            [[python, "scripts/run_ci_tests.py"]],
            {"TEST_PROFILE": "current", "BLUEPRINTS_ONLY": "true"},
        ),
        "frontend": (
            [["npm", "run", "test:frontend:unit"], ["npm", "run", "test:frontend"]],
            {},
        ),
        "translations": ([["npm", "run", "test:translations"]], {}),
        "documentation": ([["npm", "run", "test:docs"]], {}),
        "package": (
            [
                [python, "scripts/check_manifest.py"],
                [python, "scripts/check_localization.py"],
                [python, "scripts/check_release_build.py"],
            ],
            {},
        ),
        "automation": (
            [
                [python, "scripts/setup_actionlint.py"],
                ["npm", "run", "test:automation"],
            ],
            {},
        ),
        "audit": ([audit], {}),
    }
    return groups[group]


def command_plan(selected: dict[str, bool], python: str, **options):
    """Run only selected local groups; upstream HACS/hassfest is explicit."""
    return [
        (name, *group_commands(name, python, **options))
        for name in (
            "lint",
            "backend",
            "blueprints",
            "frontend",
            "translations",
            "documentation",
            "package",
            "automation",
            "audit",
        )
        if selected.get(name)
    ]
