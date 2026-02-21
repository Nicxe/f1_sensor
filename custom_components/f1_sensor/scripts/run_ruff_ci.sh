#!/usr/bin/env bash
set -euo pipefail

desired_ruff_version="0.15.2"
ruff_cmd=(ruff)

have_desired_version() {
  "$@" --version 2>/dev/null | grep -q " ${desired_ruff_version}$"
}

if have_desired_version ruff; then
  ruff_cmd=(ruff)
elif have_desired_version python3 -m ruff; then
  ruff_cmd=(python3 -m ruff)
elif command -v pipx >/dev/null 2>&1; then
  ruff_cmd=(pipx run "ruff==${desired_ruff_version}")
elif command -v ruff >/dev/null 2>&1; then
  echo "Warning: Ruff ${desired_ruff_version} not available, using installed version: $(ruff --version)"
  ruff_cmd=(ruff)
else
  echo "Ruff is not available. Install it with Homebrew (brew install ruff) or pipx."
  exit 1
fi

# Match current GitHub Action lint profile:
# ruff check custom_components, with rules configured in pyproject.toml:
#   select = E,F,W,I,UP,B,C4
#   ignore = E501
#   target-version = py313
# In this Home Assistant custom-component workspace, lint this integration directory.
target_dir="."
check_args=(
  --no-cache
  --select E,F,W,I,UP,B,C4
  --ignore E501
  --target-version py313
  --line-length 88
  --exclude tests
)
if [[ -d "custom_components/f1_sensor" ]]; then
  target_dir="custom_components/f1_sensor"
fi

check_args+=("${target_dir}")

echo "Running (CI-equivalent): ${ruff_cmd[*]} check ${check_args[*]}"
"${ruff_cmd[@]}" check \
  "${check_args[@]}"
