#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

COVERAGE="${COVERAGE:-}"
F1_TEST_ROOT="custom_components/f1_sensor/tests"

usage() {
  cat <<'EOF'
Usage: ./scripts/run_tests.sh [--full | --smoke | <pytest path or node id> ...]

With no arguments or --full, run the complete F1 Sensor Python suite.
With --smoke, run the Home Assistant lifecycle and regression smoke suite.
With one or more pytest targets, run only those targets.

Performance tests are reserved for the scheduled maintenance workflow.
EOF
}

SMOKE_TESTS=(
  "$F1_TEST_ROOT/test_setup.py"
  "$F1_TEST_ROOT/test_config_flow_entity_naming.py"
  "$F1_TEST_ROOT/test_config_flow_behavior_matrix.py"
  "$F1_TEST_ROOT/test_storage.py"
  "$F1_TEST_ROOT/test_helpers.py"
  "$F1_TEST_ROOT/test_coordinator.py"
  "$F1_TEST_ROOT/test_device_trigger.py"
  "$F1_TEST_ROOT/test_diagnostics.py"
  "$F1_TEST_ROOT/test_frontend.py"
  "$F1_TEST_ROOT/test_session_clock.py"
  "$F1_TEST_ROOT/test_auth.py"
  "$F1_TEST_ROOT/test_auth_http.py"
  "$F1_TEST_ROOT/test_auth_renewal.py"
  "$F1_TEST_ROOT/test_auth_renewal_lifecycle.py"
  "$F1_TEST_ROOT/test_button.py"
  "$F1_TEST_ROOT/test_weather.py"
  "$F1_TEST_ROOT/test_track_map_websocket.py"
  "$F1_TEST_ROOT/test_replay_lifecycle.py"
  "$F1_TEST_ROOT/test_shared_jolpica_lifecycle.py"
  "$F1_TEST_ROOT/test_websocket_reload_regression.py"
  "$F1_TEST_ROOT/test_analysis_delay_regression.py"
  "$F1_TEST_ROOT/test_analysis_no_spoiler_regression.py"
  "$F1_TEST_ROOT/test_live_window_replay_ownership.py"
  "$F1_TEST_ROOT/test_replay_analysis_return_to_live.py"
  "$F1_TEST_ROOT/test_live_bus_close_ownership.py"
  "$F1_TEST_ROOT/test_driver_best_lap.py"
  "$F1_TEST_ROOT/test_race_control_snapshots.py"
)

PYTEST_ARGS=(--)
case "${1:-}" in
  ""|--full)
    TEST_PATHS=("$F1_TEST_ROOT")
    [[ $# -eq 0 ]] || shift
    PYTEST_ARGS=("$@" --)
    ;;
  --smoke)
    TEST_PATHS=("${SMOKE_TESTS[@]}")
    shift
    PYTEST_ARGS=("$@" --)
    ;;
  --help|-h)
    usage
    exit 0
    ;;
  -*)
    TEST_PATHS=("$F1_TEST_ROOT")
    PYTEST_ARGS=("$@" --)
    ;;
  *)
    TEST_PATHS=("$@")
    ;;
esac

if [[ -n "$COVERAGE" ]]; then
  python3.14 -m pytest -q --cov=custom_components.f1_sensor --cov-report=term-missing -m 'not performance' \
    "${TEST_PATHS[@]}" "${PYTEST_ARGS[@]}"
else
  python3.14 -m pytest -q -m 'not performance' "${TEST_PATHS[@]}" "${PYTEST_ARGS[@]}"
fi
