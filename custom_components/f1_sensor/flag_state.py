from __future__ import annotations

from datetime import datetime, timezone
import asyncio


class FlagState:
    """Tracks global flag state with proper priority."""

    # --- init -------------------------------------------------------
    def __init__(self):
        self.track_flag: str | None = None  # green / red / chequered
        self.vsc_mode: str | None = None  # "VSC" / "SC" / None
        self.active_yellows: set[int] = set()  # sector-IDs
        self.state = "green"
        self.last_change: datetime = datetime.now(timezone.utc)
        self.last_seen_utc: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = asyncio.Lock()

    # --- private helpers -------------------------------------------
    def _recalculate(self) -> str:
        """Priority: RED > CHEQUERED > SC/VSC > YELLOW > GREEN"""
        if self.track_flag == "red":
            return "red"
        if self.track_flag == "chequered":
            return "chequered"
        if self.vsc_mode:
            return "vsc" if "VIRTUAL" in self.vsc_mode else "sc"
        if self.active_yellows:
            return "yellow"
        return "green"

    # --- public API -------------------------------------------------
    async def apply(self, rc: dict) -> tuple[str | None, dict]:
        """
        Update internal status. Return (new_state | None, attributes).
        Attributes are always returned for convenience.
        """
        cat = rc["category"]
        scope = rc.get("scope")
        flag = rc.get("flag")

        utc_raw = rc.get("Utc") or rc.get("utc")
        if utc_raw:
            rc_time = datetime.fromisoformat(str(utc_raw).replace("Z", "+00:00"))
            if rc_time.tzinfo is None:
                rc_time = rc_time.replace(tzinfo=timezone.utc)
        else:
            rc_time = datetime.now(timezone.utc)

        async with self._lock:
            if rc_time <= self.last_seen_utc:
                attrs = {
                    "active_sectors": sorted(self.active_yellows),
                    "track_flag": self.track_flag,
                    "sc_mode": self.vsc_mode,
                    "last_state_change": self.last_change.isoformat(),
                }
                return None, attrs

            # SAFETY CAR / VSC --------------------------------------
            if cat == "SafetyCar":
                status = rc.get("Status", "").upper()
                if "DEPLOYED" in status:
                    self.vsc_mode = rc["Mode"]
                elif status in ("ENDING", "IN THIS LAP"):
                    self.vsc_mode = None

        # TRACK-WIDE FLAGGORS ---------------------------------------
            elif cat == "Flag" and scope == "Track":
                if flag in ("GREEN", "RED", "CHEQUERED"):
                    if (
                        flag == "GREEN"
                        and self.track_flag == "red"
                        and (datetime.now(timezone.utc) - rc_time).total_seconds()
                        > 30
                    ):
                        pass
                    else:
                        # GREEN låser upp chequered och rensar red
                        self.track_flag = flag.lower()
                        if flag.lower() in ("green", "red"):
                            self.active_yellows.clear()

        # SEKTORFLAGGOR --------------------------------------------
            elif cat == "Flag" and scope == "Sector":
                sector = rc["sector"]
                if flag in ("YELLOW", "DOUBLE YELLOW"):
                    self.active_yellows.add(sector)
                elif flag == "CLEAR":
                    self.active_yellows.discard(sector)

        # --- compute new state ------------------------------------
            new_state = self._recalculate()
            changed = None
            if new_state != self.state:
                if {self.state, new_state} <= {"green", "yellow"}:
                    await asyncio.sleep(0.5)
                    new_state2 = self._recalculate()
                    if new_state2 != new_state:
                        new_state = new_state2
                self.state = new_state
                self.last_change = datetime.now(timezone.utc)
                changed = new_state
            self.last_seen_utc = rc_time

            attrs = {
                "active_sectors": sorted(self.active_yellows),
                "track_flag": self.track_flag,
                "sc_mode": self.vsc_mode,
                "last_state_change": self.last_change.isoformat(),
            }
            return changed, attrs

