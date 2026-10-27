# Bronze evidence

This register links the internal quality-scale checklist to executable evidence. It is reviewed whenever a checklist status changes.

| Capability | Evidence |
|---|---|
| UI config flow and duplicate prevention | `tests/test_config_flow_entity_naming.py`, `tests/test_setup.py` |
| Stable unique IDs, entity names, devices and diagnostics | `tests/test_entity_naming.py`, `tests/test_diagnostics.py` |
| Runtime data ownership and unload/reload cleanup | `tests/test_setup.py`, `tests/test_no_spoiler.py`, websocket lifecycle suites |
| Integration-owned polling and unavailable state | coordinator, weather, Jolpica and live-window suites |
| Reauthentication and repair paths | `tests/test_auth.py`, `tests/test_auth_http.py`, `tests/test_auth_repairs.py` |
| User-facing translations | `scripts/check_translations.py` plus browser rendering and fallback checks |
| Frontend actions and accessibility | `frontend-tests/quality.spec.js` checks every discovered card/editor and independently protects the supported-card baseline |

CI requires strictly more than 95 percent runtime Python line coverage globally. Module and branch percentages are review signals, not independent percentage gates. Test helpers and offline geometry maintenance tools are excluded. Authentication, migration, lifecycle, live windows, replay and thread safety retain blocking behavior regressions; percentages alone do not establish correctness or official Home Assistant certification. Build and automation tools have separate offline tests.
