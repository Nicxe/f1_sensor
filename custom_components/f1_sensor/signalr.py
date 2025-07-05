import json
import logging

from . import rc_transform

_LOGGER = logging.getLogger(__name__)


class SignalRClient:
    """Minimal SignalR client to handle F1 Race Control messages."""

    def __init__(self, hass, ws, t0):
        self._hass = hass
        self._ws = ws
        self._t0 = t0

    async def listen(self):
        """Listen for incoming websocket messages."""
        async for raw in self._ws:
            payload = json.loads(raw)

            # A. Push frames containing compressed packages
            if "M" in payload:
                for hub_msg in payload["M"]:
                    if hub_msg.get("A"):
                        await self._handle_rc(hub_msg["A"][0])

            # B. Result frames (history/bulk), already JSON
            elif "R" in payload and "RaceControlMessages" in payload["R"]:
                for msg in payload["R"]["RaceControlMessages"]["Messages"]:
                    await self._handle_rc(msg)

    async def _handle_rc(self, rc_raw):
        try:
            clean = rc_transform.clean_rc(rc_raw, self._t0)
            await self._hass.states.async_set(
                "sensor.f1_flag", clean.get("flag", "UNKNOWN"), clean
            )
        except Exception as exc:
            _LOGGER.warning(
                "Race control transform failed: %s", exc, exc_info=True
            )
