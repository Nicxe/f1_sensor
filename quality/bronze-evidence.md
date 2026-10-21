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
| Frontend actions and accessibility | `frontend-tests/quality.spec.js` across 23 cards, 23 editors and the compatibility alias |

CI requires strictly more than 95 percent line coverage both globally and in every shipped Python module. Test helpers and offline geometry maintenance tools are excluded. Branch coverage is reported without a blocking threshold. Authentication, migration, lifecycle, live windows and replay additionally require behavior regressions; percentages alone do not establish correctness or official Home Assistant certification. Build and automation tools have separate offline tests.
