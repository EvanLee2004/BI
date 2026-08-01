#!/usr/bin/env bash
# 将仓库 kanban.service 安装到 systemd（对齐 Restart=on-failure + StartLimit）。
# 用法（生产机）：
#   bash deploy/linux/install_systemd_unit.sh
# 需要 sudo（passwordless 或交互）。禁止把密码写进脚本/仓库。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/deploy/linux/kanban.service"
DST=/etc/systemd/system/kanban.service

if [ ! -f "$SRC" ]; then
  echo "[unit] FAIL: missing $SRC"
  exit 1
fi

echo "[unit] backup existing (if any) → /etc/systemd/system/kanban.service.bak.$(date +%Y%m%d%H%M%S)"
if [ -f "$DST" ]; then
  sudo cp -a "$DST" "${DST}.bak.$(date +%Y%m%d%H%M%S)"
fi

echo "[unit] install $SRC → $DST"
sudo cp "$SRC" "$DST"
sudo systemctl daemon-reload
echo "[unit] show Restart=…"
systemctl show kanban -p Restart -p StartLimitBurst -p StartLimitIntervalUSec --no-pager
RESTART="$(systemctl show kanban -p Restart --value)"
if [ "$RESTART" != "on-failure" ]; then
  echo "[unit] FAIL: expected Restart=on-failure got $RESTART"
  exit 2
fi
echo "[unit] OK Restart=on-failure"
# 不强制 restart 服务（仅对齐 unit）；需要生效可 systemctl restart kanban
exit 0
