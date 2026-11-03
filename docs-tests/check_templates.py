"""Render fenced documentation templates with Home Assistant's real sandbox.

Run from the repository root:
    .venv-ci/bin/python docs-tests/check_templates.py

Each fenced ``jinja2`` example is rendered against every JSON object on its
page, then with absent attributes and unknown/unavailable sensor states. The
page's first one-line ``text`` example supplies its normal sensor state.
Warnings and errors fail the check, as do example reads missing from a JSON
fixture. No Home Assistant instance is started and no service or network calls
are made: states/state_attr are fixture functions inside the actual HA sandbox.

This checks the fenced examples, not Jinja embedded inside YAML, actual entity
registration, service schemas, feed correctness or every intended output. It
does not prove that a template's business logic is correct for all payloads.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import tempfile
import warnings

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

REPOSITORY = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CodeBlock:
    """A fenced example and its location in the source page."""

    language: str
    body: str
    line: int


def code_blocks(text: str) -> list[CodeBlock]:
    """Read backtick or tilde fences without mistaking nested fence contents."""
    blocks: list[CodeBlock] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})([\w-]*)(?:[ \t].*)?$", lines[index])
        if not opening:
            index += 1
            continue
        marker, language = opening.groups()
        start = index + 1
        closing = re.compile(
            rf"^ {{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$"
        )
        index = start
        while index < len(lines) and not closing.match(lines[index]):
            index += 1
        blocks.append(CodeBlock(language, "\n".join(lines[start:index]), start + 1))
        index += 1
    return blocks


class TemplateWarnings(logging.Handler):
    """Capture HA template warnings as check failures."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def render_case(
    hass: HomeAssistant,
    block: CodeBlock,
    attributes: dict,
    state: str | None,
    *,
    example: bool,
    captured: TemplateWarnings,
) -> list[str]:
    """Render one scenario and report missing fixture data and diagnostics."""
    problems: list[str] = []

    def state_attr(entity_id: str, attribute: str):
        if example and attribute not in attributes:
            problems.append(
                f"JSON fixture has no {attribute!r}, requested for {entity_id}"
            )
        return attributes.get(attribute)

    def states(entity_id: str) -> str:
        if state is None:
            problems.append(f"No one-line text state example for {entity_id}")
        return state if state is not None else "unknown"

    captured.messages.clear()
    with warnings.catch_warnings(record=True) as python_warnings:
        warnings.simplefilter("always")
        try:
            Template(block.body, hass).async_render(
                {"state_attr": state_attr, "states": states}, parse_result=False
            )
        except Exception as error:  # Report all examples in one run.
            problems.append(str(error))
    problems.extend(captured.messages)
    problems.extend(str(warning.message) for warning in python_warnings)
    return list(dict.fromkeys(problems))


async def check_templates() -> int:
    """Check current documentation fixtures, keeping failures source-located."""
    failures: list[str] = []
    template_count = page_count = scenario_count = 0
    captured = TemplateWarnings()
    logger = logging.getLogger("homeassistant.helpers.template")
    logger.addHandler(captured)
    try:
        with tempfile.TemporaryDirectory(prefix="f1-docs-template-") as config_dir:
            hass = HomeAssistant(config_dir)
            try:
                for page in sorted((REPOSITORY / "docs").rglob("*")):
                    if page.suffix not in {".md", ".mdx"}:
                        continue
                    blocks = code_blocks(page.read_text(encoding="utf-8"))
                    templates = [
                        block for block in blocks if block.language == "jinja2"
                    ]
                    if not templates:
                        continue
                    page_count += 1
                    relative_path = page.relative_to(REPOSITORY)
                    fixtures: list[tuple[str, dict]] = []
                    for block in blocks:
                        if block.language != "json":
                            continue
                        try:
                            payload = json.loads(block.body)
                        except json.JSONDecodeError as error:
                            failures.append(
                                f"{relative_path}:{block.line}: JSON fixture: {error}"
                            )
                            continue
                        if isinstance(payload, dict):
                            fixtures.append((f"JSON at line {block.line}", payload))
                    state = next(
                        (
                            block.body.strip()
                            for block in blocks
                            if block.language == "text"
                            and len(block.body.strip().splitlines()) == 1
                        ),
                        None,
                    )
                    if not fixtures:
                        fixtures = [("state-only example", {})]
                    for block in templates:
                        template_count += 1
                        scenarios = [
                            (label, data, state, True) for label, data in fixtures
                        ]
                        scenarios.extend(
                            (f"missing / {value}", {}, value, False)
                            for value in ("unknown", "unavailable")
                        )
                        for label, attributes, sensor_state, example in scenarios:
                            scenario_count += 1
                            for problem in render_case(
                                hass,
                                block,
                                attributes,
                                sensor_state,
                                example=example,
                                captured=captured,
                            ):
                                failures.append(
                                    f"{relative_path}:{block.line} [{label}]: {problem}"
                                )
            finally:
                await hass.async_stop()
    finally:
        logger.removeHandler(captured)

    if not template_count:
        failures.append("No fenced jinja2 examples found in docs")
    print(
        f"Checked {template_count} templates in {page_count} pages: {scenario_count} renders"
    )
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"{len(failures)} errors or warnings")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check_templates()))
