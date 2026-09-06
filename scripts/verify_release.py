#!/usr/bin/env python3
"""Independently verify the bytes and metadata of the archive being released."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

REQUIRED = {
    "manifest.json",
    "__init__.py",
    "config_flow.py",
    "const.py",
    "translations/en.json",
    "www/f1-sensor-live-data-card/f1-sensor-live-data-card.js",
}


def verify_release(path: Path, version: str) -> None:
    checksum = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise ValueError("archive checksum does not match")
    sbom = json.loads(path.with_suffix(path.suffix + ".spdx.json").read_text())
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("invalid SPDX version")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not REQUIRED.issubset(names):
            raise ValueError("release has missing or duplicate runtime files")
        for name in names:
            if (
                PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or "\\" in name
            ):
                raise ValueError("unsafe archive path")
            if "tests" in PurePosixPath(name).parts or "__pycache__" in name:
                raise ValueError("non-runtime file in release")
            if name.endswith(".py"):
                compile(archive.read(name), name, "exec")
        if json.loads(archive.read("manifest.json"))["version"] != version:
            raise ValueError("release manifest version mismatch")
        assignments = ast.parse(archive.read("const.py")).body
        development = [
            n.value
            for n in assignments
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "ENABLE_DEVELOPMENT_MODE_UI"
                for t in n.targets
            )
        ]
        if len(development) != 1 or ast.literal_eval(development[0]) is not False:
            raise ValueError("development UI must be disabled in releases")
        by_name = {f["fileName"]: f for f in sbom["files"]}
        if set(by_name) != set(names) or len(by_name) != len(sbom["files"]):
            raise ValueError("SBOM does not match archive contents")
        sha1s = []
        for name in names:
            data = archive.read(name)
            hashes = {
                h["algorithm"]: h["checksumValue"] for h in by_name[name]["checksums"]
            }
            sha1 = hashlib.sha1(data).hexdigest()
            if (
                hashes.get("SHA1") != sha1
                or hashes.get("SHA256") != hashlib.sha256(data).hexdigest()
            ):
                raise ValueError(f"SBOM checksum mismatch: {name}")
            sha1s.append(sha1)
        package = sbom["packages"][0]
        expected = hashlib.sha1("".join(sorted(sha1s)).encode()).hexdigest()
        if (
            package["packageVerificationCode"]["packageVerificationCodeValue"]
            != expected
        ):
            raise ValueError("invalid SPDX package verification code")
        if package["versionInfo"] != version:
            raise ValueError("SBOM version mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    verify_release(args.archive, args.version)
    print("Release manifest, runtime files, checksum and SPDX evidence verified")


if __name__ == "__main__":
    main()
