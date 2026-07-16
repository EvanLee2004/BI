#!/bin/sh
# 任务书46·6：负载脚本（hey/oha 可选）
# 用法：BASE=http://127.0.0.1:8018 COOKIE='...' sh scripts/load_vm.sh
set -e
BASE="${BASE:-http://127.0.0.1:8018}"
OUT="${OUT:-/tmp/kanban_load.txt}"
URL="$BASE/api/v1/vm/cockpit"
if command -v hey >/dev/null 2>&1; then
  hey -z 2m -c 50 -H "Cookie: $COOKIE" "$URL" | tee "$OUT"
elif command -v oha >/dev/null 2>&1; then
  oha -z 2m -c 50 -H "Cookie: $COOKIE" "$URL" | tee "$OUT"
else
  echo "hey/oha 未安装：用 curl 冒烟 20 次" | tee "$OUT"
  i=0
  while [ $i -lt 20 ]; do
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Cookie: $COOKIE" "$URL" || echo err)
    echo "req $i -> $code" | tee -a "$OUT"
    i=$((i + 1))
  done
fi
