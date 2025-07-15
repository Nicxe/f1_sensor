from __future__ import annotations

import asyncio


class FlagState:
    """State machine tracking track flags and safety car status."""

    def __init__(self) -> None:
        self.track_flag: str | None = None
        self.vsc_mode: str | None = None
        self.active_yellows: set[int] = set()
        self.state = "green"

    # --------------------------------------------------
    def _recalculate(self) -> str:
        if self.track_flag == "red":
            return "red"
        if self.track_flag == "chequered":
            return "chequered"
        if self.vsc_mode:
            return "vsc" if "VIRTUAL" in self.vsc_mode else "sc"
        if self.active_yellows:
            return "yellow"
        return "green"

    # --------------------------------------------------
    async def apply(self, rc: dict) -> str | None:
        cat = rc["category"]
        scope = rc.get("scope")
        flag = rc.get("flag")

        # SAFETY CAR / VSC -----------------------------------------
        if cat == "SafetyCar":
            status = rc.get("Status", "").upper()
            if "DEPLOYED" in status:
                self.vsc_mode = rc.get("Mode")
            elif status in ("ENDING", "IN THIS LAP"):
                self.vsc_mode = None

        # TRACK-OMFATTANDE FLAGGOR ---------------------------------
        elif cat == "Flag" and scope == "Track":
            if flag in ("GREEN", "RED", "CHEQUERED"):
                self.track_flag = flag.lower()
                self.active_yellows.clear()
            elif flag == "CLEAR":
                self.track_flag = None
                self.active_yellows.clear()

        # SEKTORFLAGGOR --------------------------------------------
        elif cat == "Flag" and scope == "Sector":
            sector = rc.get("sector")
            if flag in ("YELLOW", "DOUBLE YELLOW") and sector is not None:
                self.active_yellows.add(int(sector))
            elif flag == "CLEAR" and sector is not None:
                self.active_yellows.discard(int(sector))

        new_state = self._recalculate()
        if new_state != self.state:
            if {self.state, new_state} == {"green", "yellow"}:
                await asyncio.sleep(0.5)
            self.state = new_state
            return new_state
        return None
