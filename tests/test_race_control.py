from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location(
    "helpers", Path("custom_components/f1_sensor/helpers.py")
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
parse_racecontrol = helpers.parse_racecontrol


def test_parse_racecontrol_returns_last_message():
    text = Path('tests/fixtures/racecontrol.jsonstream').read_text()
    msg = parse_racecontrol(text)
    assert msg['Message'] == 'CLEAR IN TRACK SECTOR 3'
