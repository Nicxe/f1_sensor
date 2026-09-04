"""Release checks must reject incomplete packages and invalid evidence."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.build_release import _runtime_files
from scripts.verify_release import verify_release


class ReleaseTests(unittest.TestCase):
    def test_unclassified_runtime_directory_is_not_silently_omitted(self):
        policy = json.loads(Path("quality/release-allowlist.json").read_text())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "new_provider").mkdir()
            (root / "new_provider" / "client.py").write_text("value = 1")
            with self.assertRaisesRegex(ValueError, "outside release allowlist"):
                _runtime_files(root, policy)

    def test_actual_archive_evidence_and_tampering(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "release.zip"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/build_release.py",
                    "--component",
                    "custom_components/f1_sensor",
                    "--output",
                    str(output),
                    "--version",
                    "0.0.0-ci",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            verify_release(output, "0.0.0-ci")
            with self.assertRaisesRegex(ValueError, "version mismatch"):
                verify_release(output, "0.0.1")
            evidence = output.with_suffix(".zip.spdx.json")
            sbom = json.loads(evidence.read_text())
            sbom["packages"][0]["packageVerificationCode"][
                "packageVerificationCodeValue"
            ] = "0" * 40
            evidence.write_text(json.dumps(sbom))
            with self.assertRaisesRegex(ValueError, "verification code"):
                verify_release(output, "0.0.0-ci")
            output.write_bytes(output.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "archive checksum"):
                verify_release(output, "0.0.0-ci")


if __name__ == "__main__":
    unittest.main()
