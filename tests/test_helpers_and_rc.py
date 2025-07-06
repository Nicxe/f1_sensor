import importlib.util
import sys
import types
from pathlib import Path
import gzip
import datetime

import pytest

dateutil = types.ModuleType("dateutil")
parser = types.ModuleType("dateutil.parser")
parser.parse = lambda s: datetime.datetime(2025, 1, 1)
dateutil.parser = parser
sys.modules["dateutil"] = dateutil
sys.modules["dateutil.parser"] = parser

# load helpers module
spec_h = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.helpers",
    Path("custom_components/f1_sensor/helpers.py"),
)
helpers = importlib.util.module_from_spec(spec_h)
sys.modules["custom_components.f1_sensor.helpers"] = helpers
spec_h.loader.exec_module(helpers)

# load rc_transform module
spec_r = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.rc_transform",
    Path("custom_components/f1_sensor/rc_transform.py"),
)
rc = importlib.util.module_from_spec(spec_r)
sys.modules["custom_components.f1_sensor.rc_transform"] = rc
spec_r.loader.exec_module(rc)


def test_parse_offset_and_to_utc():
    delta = helpers.parse_offset("+01:30:00")
    assert delta.total_seconds() == 5400
    dt = helpers.to_utc("2025-01-01T12:00:00", "+01:00:00")
    assert dt.isoformat().startswith("2025-01-01T11:00:00")


def test_find_next_session():
    data = {
        "Meetings": [
            {
                "Sessions": [
                    {
                        "StartDate": "2099-05-01T10:00:00",
                        "EndDate": "2099-05-01T11:00:00",
                        "GmtOffset": "+00:00:00",
                        "Key": "FP1",
                    }
                ],
                "Key": "R1",
            }
        ]
    }
    meeting, session = helpers.find_next_session(data)
    assert meeting["Key"] == "R1"
    assert session["Key"] == "FP1"


def test_clean_rc_dict_and_bytes():
    msg = {"m": 2, "f": 4, "s": 0, "utc": "2025-01-01T00:00:00Z"}
    clean = rc.clean_rc(msg, datetime.datetime.utcnow())
    assert clean["flag"] == "RED"

    payload = gzip.compress(b'{"m":2,"f":1,"s":0,"utc":0}')
    clean_b = rc.clean_rc(payload, datetime.datetime.utcnow())
    assert clean_b["flag"] == "GREEN"
