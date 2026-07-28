#!/usr/bin/env bash
# 2.7.3 运维：关闭维护模式
# 用法：bash deploy/linux/maintenance_off.sh
set -u
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
PYTHONPATH=src "$PY" -c "from maintenance_mode import turn_off, is_on; turn_off(); print('maintenance OFF; is_on=', is_on())"
