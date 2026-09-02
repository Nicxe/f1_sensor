#!/usr/bin/env python3
"""Build a deterministic, runtime-only F1 Sensor release and its evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ZIP_TIME = (2026, 8, 31, 0, 0, 0)
TEXT_EXTENSIONS = {".json", ".py", ".yaml", ".js"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    "assigned secret": re.compile(
        r"(?i)\b(?:access[_-]?token|api[_-]?key|password|client[_-]?secret)\b\s*[:=]\s*['\"][^'\"]{8,}"
    ),
}


def _runtime_files(component: Path, policy: dict[str, object]) -> list[Path]:
    excluded_dirs = set(policy["excluded_directories"])
    excluded_files = set(policy["excluded_files"])
    allowed_extensions = set(policy["allowed_extensions"])
    allowed_directories = set(policy["allowed_directories"])
    files: list[Path] = []
    for path in component.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(component)
        if any(part in excluded_dirs for part in relative.parts):
            continue
        if relative.name in excluded_files:
            continue
        if path.suffix not in allowed_extensions:
            continue
        if len(relative.parts) > 1 and relative.parts[0] not in allowed_directories:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(component).as_posix())


def _content(path: Path, component: Path, version: str) -> bytes:
    content = path.read_bytes()
    if path == component / "manifest.json":
        manifest = json.loads(content)
        manifest["version"] = version
        content = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    if path.suffix in TEXT_EXTENSIONS:
        text = content.decode("utf-8")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                raise ValueError(f"possible {name} in {path}")
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--policy", type=Path, default=Path("quality/release-allowlist.json")
    )
    args = parser.parse_args()
    component = args.component.resolve()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    files = _runtime_files(component, policy)
    if not files:
        raise ValueError("release allowlist selected no runtime files")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    with zipfile.ZipFile(
        args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in files:
            relative = path.relative_to(component).as_posix()
            content = _content(path, component, args.version)
            info = zipfile.ZipInfo(relative, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
            entries.append(
                {
                    "fileName": relative,
                    "checksums": [
                        {
                            "algorithm": "SHA256",
                            "checksumValue": hashlib.sha256(content).hexdigest(),
                        }
                    ],
                }
            )

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    checksum_path = args.output.with_suffix(args.output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {args.output.name}\n", encoding="utf-8")
    namespace_hash = hashlib.sha256(
        f"f1-sensor:{args.version}:{digest}".encode()
    ).hexdigest()
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"F1 Sensor {args.version}",
        "documentNamespace": f"https://github.com/Nicxe/f1_sensor/spdx/{namespace_hash}",
        "creationInfo": {
            "created": datetime(*ZIP_TIME, tzinfo=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "creators": ["Tool: scripts/build_release.py"],
        },
        "packages": [
            {
                "name": "f1_sensor",
                "SPDXID": "SPDXRef-Package-f1-sensor",
                "versionInfo": args.version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "packageVerificationCode": {
                    "packageVerificationCodeValue": hashlib.sha1(
                        "".join(
                            entry["checksums"][0]["checksumValue"] for entry in entries
                        ).encode()
                    ).hexdigest()
                },
            }
        ],
        "files": [
            {
                "SPDXID": f"SPDXRef-File-{index}",
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                **entry,
            }
            for index, entry in enumerate(entries, 1)
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-Package-f1-sensor",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": f"SPDXRef-File-{index}",
            }
            for index in range(1, len(entries) + 1)
        ],
    }
    args.output.with_suffix(args.output.suffix + ".spdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Built {args.output} with {len(entries)} runtime files ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
