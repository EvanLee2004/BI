#!/usr/bin/env bash
# 2.7.3 运维：打开维护模式（用户端显示「系统正在更新中」）
# 用法：bash deploy/linux/maintenance_on.sh [reason]
# reason 默认 manual；可选 update|restart|boot|manual
set -u
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
REASON="${1:-manual}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
PYTHONPATH=src "$PY" -c "from maintenance_mode import turn_on; p=turn_on('${REASON}'); print('maintenance ON', p)"
