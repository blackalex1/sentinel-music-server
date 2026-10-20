#!/usr/bin/env bash
# Точка входа updater.sh (алиас к update.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/update.sh" "$@"
