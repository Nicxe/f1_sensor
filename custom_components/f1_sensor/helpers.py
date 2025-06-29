import json
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError


def parse_offset(offset_str: str) -> timedelta:
    sign = -1 if offset_str.startswith('-') else 1
    h, m, s = [int(x) for x in offset_str.lstrip('+-').split(':')]
    return sign * timedelta(hours=h, minutes=m, seconds=s)


def to_utc(date_str: str, offset_str: str) -> datetime | None:
    if not date_str:
        return None
    dt = datetime.fromisoformat(date_str)
    if offset_str:
        dt -= parse_offset(offset_str)
    return dt.replace(tzinfo=timezone.utc)


def find_next_session(data: dict):
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    meetings = data.get('Meetings', []) if data else []
    upcoming = []
    for meeting in meetings:
        for session in meeting.get('Sessions', []):
            start = to_utc(session.get('StartDate'), session.get('GmtOffset'))
            end = to_utc(session.get('EndDate'), session.get('GmtOffset'))
            session['start_utc'] = start.isoformat() if start else None
            session['end_utc'] = end.isoformat() if end else None
            if end and end >= now:
                upcoming.append((start, meeting, session))
    if not upcoming:
        return None, None
    upcoming.sort(key=lambda x: x[0])
    _, meeting, session = upcoming[0]
    return meeting, session


def parse_racecontrol(text: str):
    last = None
    for line in text.splitlines():
        if '{' not in line:
            continue
        _, json_part = line.split('{', 1)
        try:
            obj = json.loads('{' + json_part)
        except JSONDecodeError:
            continue
        msgs = obj.get('Messages')
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
        elif isinstance(msgs, dict) and msgs:
            key = max(msgs.keys(), key=lambda x: int(x))
            last = msgs[key]
    return last
