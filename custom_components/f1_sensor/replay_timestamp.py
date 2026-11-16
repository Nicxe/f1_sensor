"""The duration format shared by archive and local replay readers."""

import re

_DURATION = re.compile(
    r"(?:([0-9]+)\.)?([0-9]{2,}):([0-5][0-9]):([0-5][0-9])(?:\.([0-9]{1,6}))?"
)


def parse_replay_timestamp_ms(value: str) -> int | None:
    """Parse an elapsed [d.]HH:MM:SS[.ffffff], truncating below 1 ms.

    Hours are unbounded durations, not a 24-hour clock. None is invalid;
    zero is a valid frame timestamp. Only the documented ASCII format is used.
    """
    match = _DURATION.fullmatch(value.strip())
    if match is None:
        return None
    days, hours, minutes, seconds, fraction = match.groups()
    try:
        if days is not None and (len(hours) != 2 or int(hours) >= 24):
            return None
        return (
            (int(days or 0) * 24 + int(hours)) * 3600 + int(minutes) * 60 + int(seconds)
        ) * 1000 + int(((fraction or "") + "000")[:3])
    except ValueError:
        # Also reject an adversarially long integer without leaking a frame.
        return None
