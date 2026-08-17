from __future__ import annotations

import asyncio
import base64
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    _NO_SPOILER_MANAGER_KEY,
    _RC_LOG_RESET_EVENT,
    _RC_LOG_SERVICE,
    _RC_LOG_SERVICE_MARKER,
    CONFIG_SCHEMA,
    RACE_CONTROL_LOG_MAX_FIELD_CHARS,
    RACE_CONTROL_LOG_MAX_ITEMS,
    RaceControlCoordinator,
    RaceControlLogStore,
    _async_get_shared_jolpica_client,
    async_migrate_entry,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.f1_sensor.auth import f1tv_auth_repair_issue_id
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    PLATFORMS,
    SUPPORTED_SENSOR_KEYS,
)
from custom_components.f1_sensor.live_delay import LiveDelayReferenceController
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.runtime import F1RuntimeData
from custom_components.f1_sensor.track_map import (
    TrackMapReplayAdapter,
    TrackMapStore,
)


def test_config_schema_marks_integration_config_entry_only(caplog) -> None:
    caplog.set_level(logging.ERROR)

    assert CONFIG_SCHEMA({}) == {}
    assert CONFIG_SCHEMA({DOMAIN: {}}) == {DOMAIN: {}}
    assert "does not support YAML setup" in caplog.text


class FakeLiveBus:
    last_instance = None

    def __init__(
        self,
        _hass,
        _session,
        transport_factory=None,
        auth_header=None,
        auth_failed_callback=None,
        requested_streams=None,
        provider_registry=None,
    ) -> None:
        self._transport_factory = transport_factory
        self.auth_header = auth_header
        self.auth_failed_callback = auth_failed_callback
        self.requested_streams = frozenset(requested_streams or ())
        self.active_streams = self.requested_streams
        self.provider_registry = provider_registry
        self.stream_updates: list[frozenset[str]] = []
        self.started = False
        self.closed = False
        FakeLiveBus.last_instance = self

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_header)

    async def start(self) -> None:
        self.started = True
        self.closed = False

    async def async_close(self) -> None:
        self.started = False
        self.closed = True

    async def async_update_streams(self, streams) -> None:
        self.requested_streams = frozenset(streams)
        self.active_streams = self.requested_streams
        self.stream_updates.append(self.requested_streams)

    def subscribe(self, _stream, _callback):
        return lambda: None


def _jwt(exp: datetime) -> str:
    def _part(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return ".".join(
        (
            _part({"alg": "RS256", "typ": "JWT"}),
            _part(
                {
                    "iat": int(datetime.now(UTC).timestamp()),
                    "exp": int(exp.timestamp()),
                }
            ),
            "signature",
        )
    )


class DummyCoordinator:
    def __init__(self, *args, **kwargs) -> None:
        self.config_entry = kwargs.get("config_entry")
        self.data = kwargs.get("data", {})
        self._listeners = []
        self.closed = False

    async def async_config_entry_first_refresh(self) -> None:
        return None

    async def async_close(self) -> None:
        self.closed = True
        self._listeners.clear()

    def async_add_listener(self, update_callback):
        self._listeners.append(update_callback)

        def _unsubscribe() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _unsubscribe

    def trigger_update(self) -> None:
        for listener in list(self._listeners):
            listener()


class DummyJolpicaClient:
    instances = 0
    created: list[object] = []

    def __init__(self, *_args, **_kwargs) -> None:
        type(self).instances += 1
        type(self).created.append(self)
        self.initialized = False
        self.closed = False

    async def async_initialize(self) -> None:
        self.initialized = True

    async def async_close(self) -> None:
        self.closed = True

    def diagnostics(self) -> dict:
        return {}


class FakeReplayController:
    def __init__(self, *args, **kwargs) -> None:
        self._initialized = False
        self.closed = False

    async def async_initialize(self) -> None:
        self._initialized = True

    async def async_close(self) -> None:
        self.closed = True


class FakeLiveSupervisor:
    last_instance = None

    def __init__(self, _hass, _session_coord, _live_bus, **kwargs) -> None:
        self.availability = LiveAvailabilityTracker()
        self.fallback_source = kwargs.get("fallback_source")
        self.closed = False
        FakeLiveSupervisor.last_instance = self

    async def async_start(self) -> None:
        return None

    async def async_close(self) -> None:
        self.closed = True

    def wake(self) -> None:
        return None


class DummyRaceControlLogStore:
    def __init__(self, *args, **kwargs) -> None:
        return None

    async def async_initialize(self) -> None:
        return None

    async def async_close(self) -> None:
        return None


def _coordinator_patches(
    fia_documents_coordinator_cls=DummyCoordinator,
    f1_data_coordinator_cls=DummyCoordinator,
):
    """Return context managers that replace all coordinator classes with DummyCoordinator."""
    return (
        patch("custom_components.f1_sensor.JolpicaClient", DummyJolpicaClient),
        patch(
            "custom_components.f1_sensor.F1DataCoordinator",
            f1_data_coordinator_cls,
        ),
        patch(
            "custom_components.f1_sensor.F1SeasonResultsCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.F1SprintResultsCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.F1LapPositionProgressionCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.FiaDocumentsCoordinator",
            fia_documents_coordinator_cls,
        ),
        patch("custom_components.f1_sensor.TrackStatusCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.SessionStatusCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.SessionInfoCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.RaceControlCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.WeatherDataCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.LapCountCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.IncidentCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.LiveModeCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.SessionClockCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.LiveDriversCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.TopThreeCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.TeamRadioCoordinator", DummyCoordinator),
        patch("custom_components.f1_sensor.PitStopCoordinator", DummyCoordinator),
        patch(
            "custom_components.f1_sensor.ChampionshipPredictionCoordinator",
            DummyCoordinator,
        ),
        patch("custom_components.f1_sensor.StartingGridCoordinator", DummyCoordinator),
        patch(
            "custom_components.f1_sensor.RaceControlLogStore",
            DummyRaceControlLogStore,
        ),
    )


class FailingFiaDocumentsCoordinator(DummyCoordinator):
    last_instance = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.data = None
        FailingFiaDocumentsCoordinator.last_instance = self

    async def async_config_entry_first_refresh(self) -> None:
        err = ConfigEntryNotReady()
        err.__cause__ = RuntimeError("403, message='Forbidden'")
        raise err

    def async_set_updated_data(self, data) -> None:
        self.data = data

    def build_empty_result(self) -> dict:
        return {"event_key": None, "race": None, "documents": []}


@pytest.mark.asyncio
async def test_shared_jolpica_client_initializes_once_for_concurrent_entries(
    hass,
) -> None:
    DummyJolpicaClient.instances = 0
    with patch(
        "custom_components.f1_sensor.JolpicaClient",
        DummyJolpicaClient,
    ):
        first, second = await asyncio.gather(
            _async_get_shared_jolpica_client(hass, MagicMock(), "ua"),
            _async_get_shared_jolpica_client(hass, MagicMock(), "ua"),
        )

    assert first is second
    assert first.initialized is True
    assert DummyJolpicaClient.instances == 1


def test_integration_does_not_depend_on_recorder_or_logbook() -> None:
    manifest = json.loads(
        (Path(__file__).parents[1] / "manifest.json").read_text(encoding="utf-8")
    )

    assert "recorder" not in manifest.get("after_dependencies", [])
    assert "logbook" not in manifest.get("after_dependencies", [])


@pytest.mark.asyncio
async def test_race_control_log_store_keeps_newest_first_and_resets(hass) -> None:
    session_info = DummyCoordinator(
        data={
            "Meeting": {"Key": 1001},
            "StartDate": "2026-03-12T14:00:00Z",
            "Type": "Race",
            "Name": "Grand Prix",
        }
    )
    session_status = DummyCoordinator(data={"Status": "Started", "Started": True})
    store = RaceControlLogStore(
        hass,
        "entry-1",
        session_info_coordinator=session_info,
        session_status_coordinator=session_status,
    )
    reset_events = []
    unsub = hass.bus.async_listen(
        _RC_LOG_RESET_EVENT,
        lambda event: reset_events.append(event.data),
    )

    try:
        await store.async_initialize()

        first = store.append(
            {
                "Utc": "2026-03-12T14:01:00Z",
                "Flag": "YELLOW",
                "Message": "Yellow flag in sector 1",
            }
        )
        second = store.append(
            {
                "Utc": "2026-03-12T14:02:00Z",
                "Category": "SafetyCar",
                "Message": "Safety car deployed",
            }
        )
        await hass.async_block_till_done()

        assert first is not None
        assert second is not None
        assert [item["message"] for item in store.get_items()] == [
            "Safety car deployed",
            "Yellow flag in sector 1",
        ]
        assert [item["sequence"] for item in store.get_items()] == [2, 1]

        await store.async_clear(reason="manual")
        await hass.async_block_till_done()

        assert store.get_items() == []
        assert reset_events[-1]["reason"] == "manual"
        assert reset_events[-1]["entry_id"] == "entry-1"

        after_clear = store.append(
            {
                "Utc": "2026-03-12T14:03:00Z",
                "Flag": "GREEN",
                "Message": "Track clear",
            }
        )
        assert after_clear is not None
        assert after_clear["sequence"] == 1

        session_info.data = {
            "Meeting": {"Key": 1002},
            "StartDate": "2026-03-19T14:00:00Z",
            "Type": "Race",
            "Name": "Grand Prix",
        }
        session_info.trigger_update()
        await hass.async_block_till_done()

        assert store.get_items() == []
        assert reset_events[-1]["reason"] == "session_change"
        assert reset_events[-1]["session_key"] == "1002|2026-03-19T14:00:00Z|Grand Prix"
    finally:
        unsub()
        await store.async_close()


@pytest.mark.asyncio
async def test_race_control_log_clears_when_source_stops(hass) -> None:
    session_info = DummyCoordinator(
        data={
            "Meeting": {"Key": 1001},
            "StartDate": "2026-03-12T14:00:00Z",
            "Type": "Race",
            "Name": "Grand Prix",
        }
    )
    session_status = DummyCoordinator(data={"Status": "Started", "Started": True})
    store = RaceControlLogStore(
        hass,
        "entry-1",
        session_info_coordinator=session_info,
        session_status_coordinator=session_status,
    )
    live_state = LiveAvailabilityTracker()
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-1",
        data={CONF_OPERATION_MODE: OPERATION_MODE_LIVE},
    )
    config_entry.add_to_hass(hass)
    coordinator = RaceControlCoordinator(
        hass,
        session_coord=object(),
        bus=FakeLiveBus(None, None),
        config_entry=config_entry,
        live_state=live_state,
        log_store=store,
    )
    reset_events = []
    unsub = hass.bus.async_listen(
        _RC_LOG_RESET_EVENT,
        lambda event: reset_events.append(event.data),
    )

    try:
        await store.async_initialize()

        coordinator._deliver(  # noqa: SLF001 - targeted behavior test
            {
                "Utc": "2026-03-12T14:01:00Z",
                "Flag": "YELLOW",
                "Message": "Yellow flag in sector 1",
            }
        )
        await hass.async_block_till_done()
        assert [item["message"] for item in store.get_items()] == [
            "Yellow flag in sector 1"
        ]

        live_state.set_state(False, "replay-stopped")
        await hass.async_block_till_done()

        assert store.get_items() == []
        assert reset_events[-1]["reason"] == "replay-stopped"
    finally:
        unsub()
        await coordinator.async_close()
        await store.async_close()


@pytest.mark.asyncio
async def test_race_control_log_store_bounds_history_and_fields(hass) -> None:
    store = RaceControlLogStore(hass, "entry-1")

    try:
        await store.async_initialize()

        for idx in range(RACE_CONTROL_LOG_MAX_ITEMS + 5):
            store.append(
                {
                    "Utc": f"2026-03-12T14:{idx % 60:02d}:00Z",
                    "Category": "Other",
                    "Message": f"{idx}-"
                    + ("x" * (RACE_CONTROL_LOG_MAX_FIELD_CHARS + 10)),
                }
            )
        await hass.async_block_till_done()

        items = store.get_items()
        assert len(items) == RACE_CONTROL_LOG_MAX_ITEMS
        assert items[0]["message"].startswith(f"{RACE_CONTROL_LOG_MAX_ITEMS + 4}-")
        assert len(items[0]["message"]) == RACE_CONTROL_LOG_MAX_FIELD_CHARS
        assert all(len(item["event_id"]) == 40 for item in items)
        assert len(store.get_items(limit=1)) == 1
        assert store.get_items(limit=0) == []
    finally:
        await store.async_close()


@pytest.mark.asyncio
async def test_async_setup_entry_minimal(hass, mock_config_entry) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        mock_config_entry, PLATFORMS
    )

    entry_data = hass.data[DOMAIN][mock_config_entry.entry_id]
    assert entry_data["operation_mode"] == OPERATION_MODE_DEVELOPMENT
    assert entry_data["replay_file"] == mock_config_entry.data[CONF_REPLAY_FILE]
    assert entry_data["live_bus"].started is True
    assert isinstance(mock_config_entry.runtime_data, F1RuntimeData)
    assert isinstance(entry_data["track_map_store"], TrackMapStore)
    assert isinstance(entry_data["track_map_replay_adapter"], TrackMapReplayAdapter)
    assert entry_data["race_weather_coordinator"] is not None
    assert (
        entry_data["track_map_store"] is mock_config_entry.runtime_data.track_map_store
    )


@pytest.mark.asyncio
async def test_setup_unload_reload_flushes_and_recreates_shared_transport(
    hass,
    mock_config_entry,
) -> None:
    DummyJolpicaClient.instances = 0
    DummyJolpicaClient.created = []
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for context_manager in _coordinator_patches():
            stack.enter_context(context_manager)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        assert await async_setup_entry(hass, mock_config_entry)
        first_client = hass.data[DOMAIN][mock_config_entry.entry_id]["jolpica_client"]
        assert await async_unload_entry(hass, mock_config_entry)
        assert first_client.closed is True

        assert await async_setup_entry(hass, mock_config_entry)
        second_client = hass.data[DOMAIN][mock_config_entry.entry_id]["jolpica_client"]
        assert second_client is not first_client
        assert second_client.initialized is True
        assert await async_unload_entry(hass, mock_config_entry)

    assert second_client.closed is True
    assert DummyJolpicaClient.instances == 2


@pytest.mark.asyncio
async def test_setup_unload_is_stable_across_fifty_cycles(
    hass,
    mock_config_entry,
) -> None:
    """Repeated reloads must not leave entry runtime or live transports behind."""
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for context_manager in _coordinator_patches():
            stack.enter_context(context_manager)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        for _cycle in range(50):
            assert await async_setup_entry(hass, mock_config_entry)
            bus = hass.data[DOMAIN][mock_config_entry.entry_id]["live_bus"]
            assert bus.started is True
            assert await async_unload_entry(hass, mock_config_entry)
            assert bus.started is False
            assert mock_config_entry.entry_id not in hass.data[DOMAIN]
            assert mock_config_entry.runtime_data is None


@pytest.mark.asyncio
async def test_failed_first_refresh_rolls_back_all_started_runtime(
    hass,
    mock_config_entry,
) -> None:
    """A setup retry must not inherit tasks, transports, or entry data."""

    class _FailingCoordinator(DummyCoordinator):
        refresh_calls = 0

        async def async_config_entry_first_refresh(self) -> None:
            type(self).refresh_calls += 1
            if type(self).refresh_calls == 1:
                raise ConfigEntryNotReady("injected refresh failure")

    DummyJolpicaClient.created = []
    FakeLiveBus.last_instance = None
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for context_manager in _coordinator_patches(
            f1_data_coordinator_cls=_FailingCoordinator
        ):
            stack.enter_context(context_manager)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        with pytest.raises(ConfigEntryNotReady, match="injected refresh failure"):
            await async_setup_entry(hass, mock_config_entry)
        failed_bus = FakeLiveBus.last_instance
        failed_client = DummyJolpicaClient.created[-1]
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]
        assert mock_config_entry.runtime_data is None
        assert failed_bus is None
        assert failed_client.closed is True

        assert await async_setup_entry(hass, mock_config_entry)
        retry_bus = hass.data[DOMAIN][mock_config_entry.entry_id]["live_bus"]
        assert retry_bus is not None
        assert retry_bus.started is True
        assert isinstance(mock_config_entry.runtime_data, F1RuntimeData)
        assert await async_unload_entry(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_async_setup_entry_creates_lap_position_dependencies_when_enabled(
    hass, replay_file
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            "disabled_sensors": sorted(
                SUPPORTED_SENSOR_KEYS - {"lap_position_progression"}
            ),
        },
    )
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, entry)

    assert result is True
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["race_coordinator"] is not None
    assert entry_data["season_results_coordinator"] is not None
    assert entry_data["sprint_results_coordinator"] is not None
    assert entry_data["lap_position_progression_coordinator"] is not None


@pytest.mark.asyncio
async def test_async_setup_entry_skips_lap_position_coordinator_when_disabled(
    hass, replay_file
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS),
        },
    )
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, entry)

    assert result is True
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["lap_position_progression_coordinator"] is None
    assert entry_data["race_weather_coordinator"] is None
    assert entry_data["live_bus"] is None
    assert entry.runtime_data.live is None
    assert FakeLiveBus.last_instance is None


@pytest.mark.asyncio
async def test_async_setup_entry_live_mode_wires_event_tracker_fallback(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
        },
    )
    entry.add_to_hass(hass)
    sentinel_source = object()

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: sentinel_source,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveSupervisor.last_instance is not None
    assert FakeLiveSupervisor.last_instance.fallback_source is sentinel_source


@pytest.mark.asyncio
async def test_async_setup_entry_live_mode_exposes_auth_capability(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: f"Authorization: Bearer {token}",
        },
    )
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: object(),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveBus.last_instance is not None
    assert FakeLiveBus.last_instance.auth_header == f"Bearer {token}"
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["signalr_stream_capabilities"]["auth_enabled"] is True
    assert (
        "CarData.z"
        in entry_data["signalr_stream_capabilities"]["auth_gated_live_streams"]
    )
    assert (
        "CarData.z" in entry_data["signalr_stream_capabilities"]["active_live_streams"]
    )
    assert (
        "CarData.z"
        not in entry_data["signalr_stream_capabilities"]["public_live_streams"]
    )
    assert entry_data["f1tv_auth_status"].status == "valid"
    assert entry_data["f1tv_auth_status"].used_for_live_timing is True
    entry.async_start_reauth = MagicMock()

    FakeLiveBus.last_instance.auth_failed_callback()

    assert entry_data["signalr_stream_capabilities"]["auth_enabled"] is False
    assert entry_data["f1tv_auth_status"].status == "rejected"
    entry.async_start_reauth.assert_not_called()
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
        )
        is not None
    )
    assert await async_unload_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_uses_auth_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {token}",
        },
    )
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: object(),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveBus.last_instance is not None
    assert FakeLiveBus.last_instance.auth_header == f"Bearer {token}"
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["signalr_stream_capabilities"]["auth_enabled"] is True
    assert entry_data["f1tv_auth_status"].status == "valid"
    assert entry_data["f1tv_auth_status"].used_for_live_timing is True
    assert await async_unload_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_creates_repair_for_expired_auth_and_keeps_public_live(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    token = _jwt(datetime.now(UTC) - timedelta(hours=1))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {token}",
        },
    )
    entry.async_start_reauth = MagicMock()
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: object(),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveBus.last_instance is not None
    assert FakeLiveBus.last_instance.auth_header == ""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["signalr_stream_capabilities"]["auth_enabled"] is False
    assert entry_data["f1tv_auth_status"].status == "expired"
    entry.async_start_reauth.assert_not_called()
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
        )
        is not None
    )


@pytest.mark.asyncio
async def test_async_setup_entry_suppresses_expired_auth_when_gate_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    token = _jwt(datetime.now(UTC) - timedelta(hours=1))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {token}",
        },
    )
    entry.add_to_hass(hass)
    FakeLiveBus.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: object(),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveBus.last_instance is not None
    assert FakeLiveBus.last_instance.auth_header == ""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["signalr_stream_capabilities"]["auth_enabled"] is False
    assert entry_data["f1tv_auth_status"].status == "not_configured"

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
    )
    assert issue is None


@pytest.mark.asyncio
async def test_async_setup_entry_live_mode_registers_replay_only_components(
    hass,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
        },
    )
    entry.add_to_hass(hass)
    sentinel_tracker = object()

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.EventTrackerScheduleSource",
                lambda *_args, **_kwargs: object(),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionSupervisor",
                FakeLiveSupervisor,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.TrackStatusCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.SessionStatusCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.SessionInfoCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.RaceControlCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.WeatherDataCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch("custom_components.f1_sensor.LapCountCoordinator", DummyCoordinator)
        )
        stack.enter_context(
            patch("custom_components.f1_sensor.LiveModeCoordinator", DummyCoordinator)
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.SessionClockCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch("custom_components.f1_sensor.TopThreeCoordinator", DummyCoordinator)
        )
        stack.enter_context(
            patch("custom_components.f1_sensor.TeamRadioCoordinator", DummyCoordinator)
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveDriversCoordinator", DummyCoordinator
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.FormationStartTracker",
                lambda *_args, **_kwargs: sentinel_tracker,
            )
        )
        for name in (
            "TrackStatusCoordinator",
            "SessionStatusCoordinator",
            "SessionInfoCoordinator",
            "SessionClockCoordinator",
            "RaceControlCoordinator",
            "WeatherDataCoordinator",
            "LapCountCoordinator",
            "IncidentCoordinator",
            "LiveModeCoordinator",
            "LiveDriversCoordinator",
            "TopThreeCoordinator",
            "TeamRadioCoordinator",
            "PitStopCoordinator",
            "ChampionshipPredictionCoordinator",
        ):
            stack.enter_context(
                patch(f"custom_components.f1_sensor.{name}", DummyCoordinator)
            )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.RaceControlLogStore",
                DummyRaceControlLogStore,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor._async_register_race_control_log_interfaces",
                lambda *_args, **_kwargs: None,
            )
        )
        for cm in _coordinator_patches():
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, entry)

    assert result is True
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data["operation_mode"] == OPERATION_MODE_LIVE
    assert entry_data["formation_start_tracker"] is sentinel_tracker
    assert entry_data["incident_coordinator"] is not None
    assert entry_data["team_radio_coordinator"] is not None
    assert entry_data["pitstop_coordinator"] is not None
    assert entry_data["championship_prediction_coordinator"] is not None


@pytest.mark.asyncio
async def test_live_delay_reference_controller_rejects_formation_reference(
    hass,
) -> None:
    controller = LiveDelayReferenceController(hass, "entry-1")

    with (
        patch.object(
            controller._store,  # noqa: SLF001 - targeted storage load assertion
            "async_load",
            AsyncMock(return_value={"reference": "formation_start"}),
        ),
        patch.object(controller, "_async_commit", AsyncMock()),
    ):
        result = await controller.async_initialize("formation_start")

    assert result == "session_live"
    assert controller.current == "session_live"


@pytest.mark.asyncio
async def test_async_setup_entry_continues_when_fia_documents_fail(
    hass, mock_config_entry
):
    FailingFiaDocumentsCoordinator.last_instance = None

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.build_user_agent",
                AsyncMock(return_value="ua"),
            )
        )
        stack.enter_context(patch("custom_components.f1_sensor.LiveBus", FakeLiveBus))
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.LiveSessionCoordinator",
                DummyCoordinator,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.f1_sensor.ReplayController",
                FakeReplayController,
            )
        )
        for cm in _coordinator_patches(
            fia_documents_coordinator_cls=FailingFiaDocumentsCoordinator
        ):
            stack.enter_context(cm)
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        mock_config_entry, PLATFORMS
    )
    assert FailingFiaDocumentsCoordinator.last_instance is not None
    assert FailingFiaDocumentsCoordinator.last_instance.data == {
        "event_key": None,
        "race": None,
        "documents": [],
    }


@pytest.mark.asyncio
async def test_async_unload_entry_cleans_up_runtime_data_on_success(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
        },
    )
    entry.add_to_hass(hass)

    closed = []
    unsubscribed = []

    class _Closable:
        async def async_close(self) -> None:
            closed.append("ok")

    def _activity_unsub() -> None:
        unsubscribed.append("ok")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "activity_filter_unsub": _activity_unsub,
        "live_bus": _Closable(),
    }
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert entry.entry_id not in hass.data[DOMAIN]
    assert unsubscribed == ["ok"]
    assert closed == ["ok"]


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_runtime_data_on_failed_platform_unload(
    hass,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
        },
    )
    entry.add_to_hass(hass)

    closed = []
    unsubscribed = []

    class _Closable:
        async def async_close(self) -> None:
            closed.append("ok")

    def _activity_unsub() -> None:
        unsubscribed.append("ok")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "activity_filter_unsub": _activity_unsub,
        "live_bus": _Closable(),
    }
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    result = await async_unload_entry(hass, entry)

    assert result is False
    assert entry.entry_id in hass.data[DOMAIN]
    assert unsubscribed == []
    assert closed == []


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_domain_service_registered(
    hass,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
        },
    )
    entry.add_to_hass(hass)

    hass.services.async_register(DOMAIN, _RC_LOG_SERVICE, lambda call: None)
    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = object()
    hass.data[DOMAIN][_RC_LOG_SERVICE_MARKER] = True
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert hass.services.has_service(DOMAIN, _RC_LOG_SERVICE)


@pytest.mark.asyncio
async def test_legacy_enabled_sensor_migration_is_lossless_and_idempotent(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            "sensor_name": "F1",
            "enabled_sensors": ["next_session", "driver_standings", "retired_key"],
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    first_data = dict(entry.data)

    assert entry.version == 3
    assert entry.unique_id == DOMAIN
    assert "disabled_sensors" not in entry.data
    assert "next_race" not in entry.options["disabled_sensors"]
    assert "driver_standings" not in entry.options["disabled_sensors"]
    assert "team_radio" in entry.options["disabled_sensors"]
    assert entry.data["enabled_sensors"][-1] == "retired_key"

    assert await async_migrate_entry(hass, entry)
    assert dict(entry.data) == first_data


@pytest.mark.asyncio
async def test_async_remove_entry_removes_only_entry_owned_storage(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    remover = AsyncMock()

    with patch(
        "custom_components.f1_sensor.async_remove_entry_storage",
        remover,
    ):
        await async_remove_entry(hass, entry)

    remover.assert_awaited_once_with(hass, entry.entry_id)
