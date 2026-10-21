"""Catch hassfest ordering errors while retaining the upstream validation gate."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_manifest import validate_manifest


class ManifestTests(unittest.TestCase):
    def test_required_prefix_and_alphabetical_remainder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for manifest, valid in (
                (
                    {
                        "domain": "f1_sensor",
                        "name": "F1 Sensor",
                        "dependencies": [],
                        "version": "1",
                    },
                    True,
                ),
                (
                    {
                        "domain": "f1_sensor",
                        "name": "F1 Sensor",
                        "version": "1",
                        "dependencies": [],
                    },
                    False,
                ),
                ({"name": "F1 Sensor", "domain": "f1_sensor"}, False),
                ({"version": "1"}, False),
                ([], False),
            ):
                path.write_text(json.dumps(manifest))
                self.assertEqual(not validate_manifest(path), valid)
