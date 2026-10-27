#!/usr/bin/env python3
"""Install the same checksum-verified workflow validator locally and in CI."""

from hashlib import sha256
import io
from pathlib import Path
import platform
import subprocess
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.7.12"
CHECKSUMS = {
    (
        "Darwin",
        "arm64",
    ): "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f",
    (
        "Darwin",
        "x86_64",
    ): "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644",
    (
        "Linux",
        "x86_64",
    ): "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
    (
        "Linux",
        "aarch64",
    ): "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6",
}


def install() -> Path:
    """Extract only the verified executable; never unpack archive paths."""
    target = ROOT / ".tools-ci" / "bin" / "actionlint"
    if target.is_file():
        result = subprocess.run(
            [str(target), "--version"], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.splitlines()[0] == VERSION:
            return target
    key = (platform.system(), platform.machine())
    expected = CHECKSUMS.get(key)
    if expected is None:
        raise RuntimeError(f"No verified actionlint build for {key}")
    os_name = "darwin" if key[0] == "Darwin" else "linux"
    architecture = "arm64" if key[1] in ("arm64", "aarch64") else "amd64"
    filename = f"actionlint_{VERSION}_{os_name}_{architecture}.tar.gz"
    url = f"https://github.com/rhysd/actionlint/releases/download/v{VERSION}/{filename}"
    with urlopen(url, timeout=60) as response:
        archive = response.read()
    if sha256(archive).hexdigest() != expected:
        raise RuntimeError("actionlint archive checksum does not match")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        executable = source.extractfile("actionlint")
        if executable is None:
            raise RuntimeError("Verified archive has no actionlint executable")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(executable.read())
        target.chmod(0o755)
    return target


def main() -> int:
    command = [
        str(install()),
        "-shellcheck=",
        "-pyflakes=",
        # This read-only GitHub permission postdates the pinned validator.
        "-ignore",
        '^unknown permission scope "vulnerability-alerts"\\.',
    ]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
