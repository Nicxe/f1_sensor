#!/usr/bin/env bash
set -euo pipefail

ruff_cmd=(ruff)
if ! command -v ruff >/dev/null 2>&1; then
  if ! python3 -m ruff --version >/dev/null 2>&1; then
    python3 -m pip install --user --upgrade --break-system-packages ruff
  fi

  if command -v ruff >/dev/null 2>&1; then
    ruff_cmd=(ruff)
  elif python3 -m ruff --version >/dev/null 2>&1; then
    ruff_cmd=(python3 -m ruff)
  else
    echo "Ruff is not available. Install it with Homebrew (brew install ruff) or pipx."
    exit 1
  fi
fi

# This repository is a custom component without the Home Assistant core layout.
# Use homeassistant/tests when present, otherwise lint this integration root.
if [[ -d "homeassistant" ]]; then
  targets=(homeassistant tests)
else
  targets=(. tests)
fi

echo "Running: ${ruff_cmd[*]} format --no-cache ${targets[*]}"
"${ruff_cmd[@]}" format --no-cache "${targets[@]}"

echo "Running: ${ruff_cmd[*]} format --check --no-cache ${targets[*]}"
"${ruff_cmd[@]}" format --check --no-cache "${targets[@]}"

echo "Running: ${ruff_cmd[*]} check --no-cache ${targets[*]}"
"${ruff_cmd[@]}" check --no-cache "${targets[@]}"
