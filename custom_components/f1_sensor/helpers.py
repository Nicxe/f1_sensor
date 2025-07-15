import json
from json import JSONDecodeError


def parse_racecontrol(text: str):
    last = None
    for line in text.splitlines():
        if "{" not in line:
            continue
        _, json_part = line.split("{", 1)
        try:
            obj = json.loads("{" + json_part)
        except JSONDecodeError:
            continue
        msgs = obj.get("Messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
        elif isinstance(msgs, dict) and msgs:
            numeric_keys = [k for k in msgs.keys() if str(k).isdigit()]
            if numeric_keys:
                key = max(numeric_keys, key=lambda x: int(x))
                last = msgs[key]
                if isinstance(last, dict):
                    last.setdefault("id", int(key))
    return last
