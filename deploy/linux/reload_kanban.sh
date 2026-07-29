#!/usr/bin/env bash
# 3.1.0：无交互 sudo 的代码热加载（lee 用户）
# 优先 passwordless systemctl；否则结束 run.py --serve，由 start_with_rollback / systemd Restart 拉起。
# 禁止写密码；禁止依赖 kanban-home。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

echo "[reload] root=$ROOT $(date '+%Y-%m-%d %H:%M:%S')"

if sudo -n systemctl restart kanban >/dev/null 2>&1; then
  echo "[reload] systemctl restart kanban (passwordless sudo)"
else
  echo "[reload] no passwordless sudo; stopping run.py --serve for watchdog/systemd restart"
  # 只杀本仓库下的 serve 进程
  pids="$(ps -eo pid=,cmd= | awk -v root="$ROOT" '
    index($0, root) && /run\.py --serve/ { print $1 }
  ')"
  if [ -z "${pids}" ]; then
    echo "[reload] no matching run.py --serve; try systemctl start if unit exists"
    sudo -n systemctl start kanban >/dev/null 2>&1 || true
  else
    for pid in $pids; do
      echo "[reload] kill -TERM $pid"
      kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        echo "[reload] kill -KILL $pid"
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done
  fi
fi

# 等待 health
ok=0
for i in $(seq 1 60); do
  code="$(curl -sS -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8018/api/v1/health 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    echo "[reload] health=200 after ${i} tries"
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" != "1" ]; then
  echo "[reload] WARN: health not 200 yet (cold start may need more time)"
  exit 1
fi
if [ -f "$ROOT/VERSION" ]; then
  echo "[reload] VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")"
fi
exit 0
