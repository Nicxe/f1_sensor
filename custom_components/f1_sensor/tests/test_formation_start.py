from __future__ import annotations

from datetime import UTC, timedelta

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.formation_start import FormationStartTracker


class _CachingBus:
    def __init__(self, cached: dict[str, dict] | None = None) -> None:
        self._cached = cached or {}
        self.subscriptions: list[str] = []

    def subscribe(self, stream: str, callback):
        self.subscriptions.append(stream)
        payload = self._cached.get(stream)
        if isinstance(payload, dict):
            callback(dict(payload))
        return lambda: None


def _session_info_payload(
    *,
    session_status: str = "Inactive",
    start_utc=None,
) -> dict[str, str]:
    start = start_utc or dt_util.utcnow().replace(microsecond=0)
    return {
        "Path": "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/",
        "Type": "Race",
        "Name": "Race",
        "StartDate": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "GmtOffset": "+00:00",
        "SessionStatus": session_status,
    }


@pytest.mark.asyncio
async def test_late_session_info_does_not_rearm_after_session_goes_live(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    probe_calls: list[tuple[float, str | None]] = []

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    tracker._handle_session_info(_session_info_payload())
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "pending"

    tracker._handle_session_status({"Status": "Started", "Started": "Started"})
    tracker._handle_session_info(_session_info_payload(session_status="Started"))
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "live"

    tracker._handle_session_info(_session_info_payload(session_status="Finalised"))
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "terminal"


@pytest.mark.asyncio
async def test_started_status_cancels_pending_probe(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    start_utc = dt_util.utcnow() + timedelta(minutes=5)

    tracker._handle_session_info(_session_info_payload(start_utc=start_utc))

    assert tracker._task is not None

    tracker._handle_session_status({"Status": "Started", "Started": "Started"})

    assert tracker._task is None
    assert tracker.snapshot()["status"] == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_info_status", "session_status_payload", "expected_status"),
    [
        (
            "Started",
            {"Status": "Started", "Started": "Started"},
            "live",
        ),
        (
            "Finalised",
            {"Status": "Finalised", "Started": "Finished"},
            "terminal",
        ),
    ],
)
async def test_cached_late_payloads_do_not_schedule_probe(
    hass,
    session_info_status: str,
    session_status_payload: dict[str, str],
    expected_status: str,
) -> None:
    probe_calls: list[tuple[float, str | None]] = []
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(
            {
                "SessionInfo": _session_info_payload(
                    session_status=session_info_status
                ),
                "SessionStatus": session_status_payload,
            }
        ),
        http_session=object(),  # type: ignore[arg-type]
    )

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    snapshots: list[dict[str, str | None]] = []
    tracker.add_listener(lambda snapshot: snapshots.append(snapshot))
    await hass.async_block_till_done()

    assert probe_calls == []
    assert tracker.snapshot()["status"] == expected_status
    assert tracker.formation_start_utc is None
    assert snapshots[-1]["formation_start"] is None
