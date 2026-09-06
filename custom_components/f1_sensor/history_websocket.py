"""Versioned WebSocket API for history and bounded lap analytics."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import DOMAIN
from .jolpica import JolpicaError
from .jolpica_pagination import JolpicaPaginationError
from .runtime import F1RuntimeData, runtime_from_hass

HISTORY_WS_MARKER = "__history_ws_registered__"
HISTORY_CATALOG_WS_TYPE = f"{DOMAIN}/history/catalog"
HISTORY_RESULTS_WS_TYPE = f"{DOMAIN}/history/results"
HISTORY_LAPS_WS_TYPE = f"{DOMAIN}/history/laps"
HISTORY_LIVE_LAPS_WS_TYPE = f"{DOMAIN}/history/live_laps"


def async_register_history_websocket(hass: HomeAssistant) -> None:
    """Register history commands exactly once per Home Assistant runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(HISTORY_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_history_catalog)
    websocket_api.async_register_command(hass, _ws_get_history_results)
    websocket_api.async_register_command(hass, _ws_get_history_laps)
    websocket_api.async_register_command(hass, _ws_get_live_laps)
    root[HISTORY_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): HISTORY_CATALOG_WS_TYPE,
        vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=1950, max=2200)),
        vol.Optional("entry_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("force_refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def _ws_get_history_catalog(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor is not loaded")
        return
    await _send_async_result(
        connection,
        msg,
        runtime.history.service.async_get_catalog(
            msg["year"],
            force_refresh=msg["force_refresh"],
        ),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): HISTORY_RESULTS_WS_TYPE,
        vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=1950, max=2200)),
        vol.Required("session_key"): vol.Any(int, vol.All(str, vol.Length(min=1))),
        vol.Required("round"): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
        vol.Required("session_type"): vol.All(str, vol.Length(min=1, max=80)),
        vol.Optional("entry_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("force_refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def _ws_get_history_results(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor is not loaded")
        return
    await _send_async_result(
        connection,
        msg,
        runtime.history.service.async_get_session_results(
            year=msg["year"],
            session_key=msg["session_key"],
            round_number=msg["round"],
            session_type=msg["session_type"],
            force_refresh=msg["force_refresh"],
        ),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): HISTORY_LAPS_WS_TYPE,
        vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=1950, max=2200)),
        vol.Required("round"): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
        vol.Required("session_type"): vol.All(str, vol.Length(min=1, max=80)),
        vol.Optional("entry_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("force_refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def _ws_get_history_laps(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor is not loaded")
        return
    await _send_async_result(
        connection,
        msg,
        runtime.history.service.async_get_laps(
            year=msg["year"],
            round_number=msg["round"],
            session_type=msg["session_type"],
            force_refresh=msg["force_refresh"],
        ),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): HISTORY_LIVE_LAPS_WS_TYPE,
        vol.Optional("entry_id"): vol.All(str, vol.Length(min=1)),
    }
)
def _ws_get_live_laps(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor is not loaded")
        return
    store = runtime.history.lap_analysis
    if store is None:
        connection.send_result(
            msg["id"],
            {
                "provider": None,
                "session_id": None,
                "laps": [],
                "speed_traps": {"session_best": {}},
                "lap_quality": {"total": 0, "clean": 0, "deleted": 0, "inferred": 0},
                "coverage": {
                    "speed_traps": "live_or_replay_not_active",
                    "minisectors": "live_or_replay_not_active",
                },
            },
        )
        return
    connection.send_result(msg["id"], store.snapshot())


async def _send_async_result(
    connection: Any,
    msg: dict[str, Any],
    awaitable: Any,
) -> None:
    try:
        result = await awaitable
    except (JolpicaError, JolpicaPaginationError):
        connection.send_error(
            msg["id"], "provider_unavailable", "Historical data is unavailable"
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_request", str(err))
    except Exception:  # noqa: BLE001
        connection.send_error(
            msg["id"], "provider_unavailable", "Historical data is unavailable"
        )
    else:
        connection.send_result(msg["id"], result)


def _resolve_runtime(
    hass: HomeAssistant,
    entry_id: str | None,
) -> F1RuntimeData | None:
    if entry_id:
        return runtime_from_hass(hass, entry_id)
    runtimes = [
        runtime
        for entry in hass.config_entries.async_entries(DOMAIN)
        if (runtime := runtime_from_hass(hass, entry.entry_id)) is not None
    ]
    return runtimes[0] if len(runtimes) == 1 else None
