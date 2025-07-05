from __future__ import annotations


class FlagState:
    def __init__(self):
        self.track_red = False
        self.vsc_active = False
        self.active_yellows: set[int] = set()
        self.state = "green"

    # --------------------------------------------------
    def _recalculate(self) -> str:
        if self.track_red:
            return "red"
        if self.vsc_active:
            return "vsc"
        if self.active_yellows:
            return "yellow"
        return "green"

    # --------------------------------------------------
    def apply(self, rc: dict) -> str | None:
        """Uppdatera intern status med ett normaliserat RaceControl-objekt.
        Returnerar ny state-str\u00e4ng om n\u00e5got \u00e4ndrats, annars None.
        """
        cat, flag, scope = rc["category"], rc.get("flag"), rc["scope"]

        # --- 1) FLAG typ RED / CLEAR / YELLOW ---------------------------------
        if cat == "Flag" and flag:
            if flag == "RED" and scope == "Track":
                self.track_red = True

            elif flag in ("YELLOW", "DOUBLE YELLOW") and scope == "Sector":
                self.active_yellows.add(rc["sector"])

            elif flag == "CLEAR":
                if scope == "Sector":
                    self.active_yellows.discard(rc["sector"])
                elif scope == "Track":
                    self.track_red = False

            elif flag == "GREEN" and scope == "Track":
                # Race k\u00f6r ig\u00e5ng \u2013 rensa r\u00f6d men l\u00e4mna sektorgula
                self.track_red = False

        # --- 2) SAFETY CAR (VSC) ---------------------------------------------
        elif cat == "SafetyCar":
            if rc.get("Status") == "VSC DEPLOYED":
                self.vsc_active = True
            elif rc.get("Status") in ("VSC END", "RESUME"):
                self.vsc_active = False

        # --- 3) Ber\u00e4kna nytt state -------------------------------------------
        new_state = self._recalculate()
        if new_state != self.state:
            self.state = new_state
            return new_state
        return None
