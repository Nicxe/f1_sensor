#!/usr/bin/env python3
"""Catch deterministic Home Assistant manifest errors before remote hassfest."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Stdlib-only snapshot of hassfest's globally allowed imports and entity
# platforms. Keep these in sync when updating the HA verification profile:
# https://github.com/home-assistant/core/blob/7c3a98ae6f4454d65500438b2fb503363fcf490a/script/hassfest/dependencies.py
# https://github.com/home-assistant/core/blob/7c3a98ae6f4454d65500438b2fb503363fcf490a/homeassistant/generated/entity_platforms.py
# This is an early static check, not a replacement for remote hassfest.
ALLOWED_COMPONENTS = frozenset(
    """homeassistant persistent_notification
    ai_task air_quality alarm_control_panel assist_satellite binary_sensor button
    calendar camera climate conversation cover date datetime device_tracker event
    fan geo_location humidifier image image_processing infrared lawn_mower light
    lock media_player notify number radio_frequency remote scene select sensor
    siren stt switch text time todo tts update vacuum valve wake_word water_heater
    weather alert automation default_config device_automation frontend group
    input_boolean input_button input_datetime input_number input_select input_text
    labs media_source onboarding panel_custom person script shopping_list sun
    system_health system_log timer webhook websocket_api zone mjpeg stream""".split()
)
DISCOVERY_COMPONENTS = {
    "dhcp": ("dhcp",),
    "mqtt": ("mqtt",),
    "ssdp": ("ssdp",),
    "zeroconf": ("zeroconf", "homekit"),
}


class ComponentImports(ast.NodeVisitor):
    """Collect literal component imports without importing integration code."""

    def __init__(self) -> None:
        self.references: set[str] = set()

    def visit_If(self, node: ast.If) -> None:
        # Match hassfest's type-only import exclusion.
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for name in node.names:
            if name.name.startswith("homeassistant.components."):
                self.references.add(name.name.split(".")[2])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if (
            node.module == "homeassistant.components.http.auth"
            and len(node.names) == 1
            and node.names[0].name == "async_sign_path"
        ):
            return
        if node.module == "homeassistant.components":
            self.references.update(name.name for name in node.names)
        elif node.module and node.module.startswith("homeassistant.components."):
            self.references.add(node.module.split(".")[2])


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys rather than silently keeping the last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def dependency_errors(path: Path, manifest: dict) -> list[str]:
    """Match component references against declared and upstream-exempt domains."""
    allowed = (
        set(ALLOWED_COMPONENTS)
        | set(manifest.get("dependencies", []))
        | set(manifest.get("after_dependencies", []))
        | {manifest["domain"]}
    )
    if "bluetooth_adapters" in allowed:
        allowed.add("bluetooth")
    allowed.update(
        component
        for component, fields in DISCOVERY_COMPONENTS.items()
        if any(field in manifest for field in fields)
    )
    errors = []
    # Hassfest scans nested tests too. Test-only integrations belong in external
    # test support, not in the shipped integration's dependency contract.
    for source in sorted(path.parent.rglob("*.py")):
        if not source.is_file():
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, ValueError, SyntaxError) as error:
            errors.append(f"{source}: could not inspect component imports: {error}")
            continue
        collector = ComponentImports()
        collector.visit(tree)
        for component in sorted(collector.references - allowed):
            if (path.parent / f"{component}.py").is_file() or (
                path.parent / component
            ).is_dir():
                continue
            errors.append(
                f"{source}: component {component!r} is not declared in dependencies "
                "or after_dependencies; move test-only imports to external test support"
            )
    return errors


def validate_manifest(path: Path) -> list[str]:
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_object
        )
    except (OSError, ValueError) as error:
        return [f"{path}: {error}"]
    if not isinstance(manifest, dict):
        return [f"{path}: manifest must be an object"]
    keys = list(manifest)
    expected = ["domain", "name", *sorted(set(keys) - {"domain", "name"})]
    if keys != expected:
        return [
            f"{path}: keys must be domain, name, then the remaining keys alphabetically"
        ]
    errors = []
    for field in ("domain", "name"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            errors.append(f"{path}: {field} must be a nonempty string")
    for field in ("dependencies", "after_dependencies"):
        values = manifest.get(field, [])
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            errors.append(f"{path}: {field} must be a list of component names")
        elif len(values) != len(set(values)):
            errors.append(f"{path}: {field} contains duplicate components")
    if errors:
        return errors
    if set(manifest.get("dependencies", [])) & set(
        manifest.get("after_dependencies", [])
    ):
        return [f"{path}: a component cannot be both a dependency and after_dependency"]
    return dependency_errors(path, manifest)


def main() -> int:
    errors = validate_manifest(ROOT / "custom_components/f1_sensor/manifest.json")
    print(
        "\n".join(errors)
        if errors
        else "Home Assistant manifest and component imports passed"
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
