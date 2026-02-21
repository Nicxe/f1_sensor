from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    _is_activity_log_excluded_entity,
    _refresh_recorder_entity_filter,
    _wrap_activity_filter,
    _wrap_logbook_subscribe_events,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    PLATFORMS,
)
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker


class FakeLiveBus:
    def __init__(self, _hass, _session, transport_factory=None) -> None:
        self._transport_factory = transport_factory
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def async_close(self) -> None:
        self.started = False

    def subscribe(self, _stream, _callback):
        return lambda: None


class DummyCoordinator:
    def __init__(self, *args, **kwargs) -> None:
        self.config_entry = kwargs.get("config_entry")

    async def async_config_entry_first_refresh(self) -> None:
        return None


class FakeReplayController:
    def __init__(self, *args, **kwargs) -> None:
        self._initialized = False

    async def async_initialize(self) -> None:
        self._initialized = True


class FakeLiveSupervisor:
    last_instance = None

    def __init__(self, _hass, _session_coord, _live_bus, **kwargs) -> None:
        self.availability = LiveAvailabilityTracker()
        self.fallback_source = kwargs.get("fallback_source")
        FakeLiveSupervisor.last_instance = self

    async def async_start(self) -> None:
        return None

    def wake(self) -> None:
        return None


def _coordinator_patches():
    """Return context managers that replace all coordinator classes with DummyCoordinator."""
    return (
        patch("custom_components.f1_sensor.F1DataCoordinator", DummyCoordinator),
        patch(
            "custom_components.f1_sensor.F1SeasonResultsCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.F1SprintResultsCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.FiaDocumentsCoordinator",
            DummyCoordinator,
        ),
    )


def test_activity_log_exclude_entity_matcher() -> None:
    assert _is_activity_log_excluded_entity("sensor.f1_track_time")
    assert _is_activity_log_excluded_entity("sensor.f1_session_time_remaining")
    assert _is_activity_log_excluded_entity("sensor.f1_session_time_elapsed")
    assert _is_activity_log_excluded_entity("sensor.f1_race_time_to_three_hour_limit")
    assert not _is_activity_log_excluded_entity("sensor.f1_next_race")
    assert not _is_activity_log_excluded_entity("binary_sensor.f1_track_time")


def test_activity_log_filter_wrapper() -> None:
    def base_filter(entity_id: str) -> bool:
        return entity_id != "sensor.block_me"

    wrapped = _wrap_activity_filter(base_filter)

    assert not wrapped("sensor.f1_track_time")
    assert not wrapped("sensor.f1_session_time_remaining")
    assert not wrapped("sensor.block_me")
    assert wrapped("sensor.f1_next_race")
    assert _wrap_activity_filter(wrapped) is wrapped


def test_refresh_recorder_entity_filter_rebinds_listener() -> None:
    class _FakeRecorder:
        def __init__(self) -> None:
            self.entity_filter = None
            self.recording = True
            self.stop_calls = 0
            self.init_calls = 0

        def _async_stop_queue_watcher_and_event_listener(self) -> None:
            self.stop_calls += 1

        def async_initialize(self) -> None:
            self.init_calls += 1

    fake = _FakeRecorder()
    _refresh_recorder_entity_filter(fake)
    assert fake.stop_calls == 1
    assert fake.init_calls == 1

    # Migration case: filter is already wrapped but listener has not been rebound yet.
    fake2 = _FakeRecorder()

    def allow_all(_entity_id: str) -> bool:
        return True

    fake2.entity_filter = _wrap_activity_filter(allow_all)
    _refresh_recorder_entity_filter(fake2)
    assert fake2.stop_calls == 1
    assert fake2.init_calls == 1
    assert fake.entity_filter is not None

    # Idempotent once wrapped
    _refresh_recorder_entity_filter(fake)
    assert fake.stop_calls == 1
    assert fake.init_calls == 1


def test_logbook_subscribe_wrapper_filters_excluded_entities() -> None:
    captured: dict[str, object] = {}

    def _base_subscribe(
        _hass,
        _subscriptions,
        target,
        _event_types,
        _entities_filter,
        _entity_ids,
        _device_ids,
    ) -> None:
        captured["target"] = target

    wrapped = _wrap_logbook_subscribe_events(_base_subscribe)
    assert callable(wrapped)
    assert _wrap_logbook_subscribe_events(wrapped) is wrapped

    seen: list[str] = []

    def _target(_event) -> None:
        seen.append("called")

    wrapped(None, [], _target, (), None, None, None)
    filtered_target = captured["target"]

    # Excluded timer entity should never reach target.
    filtered_target(  # type: ignore[operator]
        SimpleNamespace(data={"entity_id": "sensor.f1_session_time_elapsed"})
    )
    assert seen == []

    filtered_target(  # type: ignore[operator]
        SimpleNamespace(data={"entity_id": "sensor.f1_race_time_to_three_hour_limit"})
    )
    assert seen == []

    # Non-excluded entity should pass through.
    filtered_target(  # type: ignore[operator]
        SimpleNamespace(data={"entity_id": "sensor.f1_next_race"})
    )
    assert seen == ["called"]


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


@pytest.mark.asyncio
async def test_async_setup_entry_live_mode_wires_event_tracker_fallback(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
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
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveSupervisor.last_instance is not None
    assert FakeLiveSupervisor.last_instance.fallback_source is sentinel_source


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
