# Bronze evidence

This register links the internal quality-scale checklist to executable evidence. It is reviewed whenever a checklist status changes.

| Capability | Evidence |
|---|---|
| UI config flow and duplicate prevention | `tests/test_config_flow_entity_naming.py`, `tests/test_setup.py` |
| Stable unique IDs, entity names, devices and diagnostics | `tests/test_entity_naming.py`, `tests/test_diagnostics.py` |
| Runtime data ownership and unload/reload cleanup | `tests/test_setup.py`, `tests/test_no_spoiler.py`, websocket lifecycle suites |
| Integration-owned polling and unavailable state | coordinator, weather, Jolpica and live-window suites |
| Reauthentication and repair paths | `tests/test_auth.py`, `tests/test_auth_http.py`, `tests/test_auth_repairs.py` |
| User-facing translations | `tests/test_phase_5_quality.py` and `scripts/check_translations.py` |
| Frontend actions and accessibility | `frontend-tests/quality.spec.js` across 23 cards, 23 editors and the compatibility alias |

The internal checklist does not claim Silver while the measured integration coverage remains below 95 percent. `quality/coverage-ratchet.json` records the current evidence and the ordered promotion targets.
