"""Install the pinned official Node distribution without npm lifecycle scripts."""

from hashlib import sha256
import io
from pathlib import Path
import platform
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = "22.23.3"
BUILDS = {
    ("Darwin", "arm64"): (
        "darwin-arm64.tar.gz",
        "23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53",
    ),
    ("Darwin", "x86_64"): (
        "darwin-x64.tar.gz",
        "8a677b0219178efd6eb0e475457c4afb452b521a92f6e67845a73bd85727f2a8",
    ),
    ("Linux", "x86_64"): (
        "linux-x64.tar.xz",
        "df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de",
    ),
    ("Linux", "aarch64"): (
        "linux-arm64.tar.xz",
        "a44aeb94849a299b22df10b9e622ec2f605c2183501bc40590705131de7c740f",
    ),
}


def runtime_directory() -> Path:
    build, _ = BUILDS[(platform.system(), platform.machine())]
    name = build.removesuffix(".tar.gz").removesuffix(".tar.xz")
    return ROOT / ".tools-ci/runtime" / f"node-v{VERSION}-{name}"


def install() -> Path:
    if (ROOT / ".node-version").read_text().strip() != VERSION:
        raise RuntimeError(
            "Update the official Node archive checksums with .node-version"
        )
    target = runtime_directory()
    if (target / "bin/node").is_file():
        return target
    build, expected = BUILDS[(platform.system(), platform.machine())]
    url = f"https://nodejs.org/dist/v{VERSION}/node-v{VERSION}-{build}"
    with urlopen(url, timeout=60) as response:
        archive = response.read()
    if sha256(archive).hexdigest() != expected:
        raise RuntimeError("Official Node archive checksum does not match")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
        source.extractall(target.parent, filter="data")
    return target
