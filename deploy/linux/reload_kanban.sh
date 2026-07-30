#!/usr/bin/env bash
# 3.5.0：代码热加载 + 真生效证明（PID 切换 + runtime version/commit）
# 优先 passwordless systemctl；否则结束 run.py --serve，由 start_with_rollback / systemd Restart 拉起。
# 禁止写密码；禁止依赖 kanban-home。
# 成功判据：旧 serve PID 消失 + 新 PID 出现 + health 200 + runtime VERSION/commit 与磁盘目标一致。
# 磁盘 VERSION 单独打印不算成功；旧进程仍 200 必须非 0。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

HEALTH_URL="${KANBAN_HEALTH_URL:-http://127.0.0.1:8018/api/v1/health}"
echo "[reload] root=$ROOT $(date '+%Y-%m-%d %H:%M:%S')"

# --- helpers ---
list_serve_pids() {
  ps -eo pid=,cmd= | awk -v root="$ROOT" '
    index($0, root) && /run\.py --serve/ { print $1 }
  '
}

first_pid() {
  list_serve_pids | head -n1 | tr -d ' '
}

# 期望版本/commit（磁盘侧目标，用于比对 runtime）
DISK_VERSION=""
if [ -f "$ROOT/VERSION" ]; then
  DISK_VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
fi
DISK_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
DISK_COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"

OLD_PID="$(first_pid)"
echo "[reload] before serve_pid=${OLD_PID:-none} disk_VERSION=${DISK_VERSION:-?} disk_commit=${DISK_COMMIT_SHORT:-?}"

# --- restart ---
if sudo -n systemctl restart kanban >/dev/null 2>&1; then
  echo "[reload] systemctl restart kanban (passwordless sudo)"
  RESTART_MODE=systemd
else
  echo "[reload] no passwordless sudo; stopping run.py --serve for watchdog/systemd restart"
  RESTART_MODE=kill
  pids="$(list_serve_pids)"
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

# --- wait: old PID gone + new PID + health 200 + runtime marker ---
ok=0
new_pid=""
runtime_version=""
runtime_commit=""
for i in $(seq 1 90); do
  # old gone?
  if [ -n "${OLD_PID}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    sleep 2
    continue
  fi
  new_pid="$(first_pid)"
  if [ -z "${new_pid}" ]; then
    sleep 2
    continue
  fi
  if [ -n "${OLD_PID}" ] && [ "${new_pid}" = "${OLD_PID}" ]; then
    # 同 PID 仍存活 → 未切换
    sleep 2
    continue
  fi

  body="$(curl -sS -m 3 "$HEALTH_URL" 2>/dev/null || true)"
  code="$(curl -sS -m 3 -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
  if [ "$code" != "200" ]; then
    sleep 2
    continue
  fi

  # 解析 runtime（localhost health 应含 version/git_commit/pid）
  runtime_version="$(printf '%s' "$body" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); m=d.get("metrics") or {}
 print(m.get("version") or d.get("version") or "")
except Exception:
 print("")' 2>/dev/null || true)"
  runtime_commit="$(printf '%s' "$body" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); m=d.get("metrics") or {}
 print(m.get("git_commit") or d.get("git_commit") or "")
except Exception:
 print("")' 2>/dev/null || true)"
  runtime_pid="$(printf '%s' "$body" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); m=d.get("metrics") or {}
 print(m.get("pid") or d.get("pid") or "")
except Exception:
 print("")' 2>/dev/null || true)"

  # 契约字段：3.5.0 起 health 带 version（本机）
  if [ -z "${runtime_version}" ]; then
    echo "[reload] try ${i}: health=200 but no runtime version yet"
    sleep 2
    continue
  fi
  if [ -n "${DISK_VERSION}" ] && [ "${runtime_version}" != "${DISK_VERSION}" ]; then
    echo "[reload] try ${i}: runtime version=${runtime_version} != disk ${DISK_VERSION}"
    sleep 2
    continue
  fi
  if [ -n "${DISK_COMMIT}" ] && [ -n "${runtime_commit}" ]; then
    case "${DISK_COMMIT}" in
      ${runtime_commit}*) ;;
      *)
        # 允许 short/full
        case "${runtime_commit}" in
          ${DISK_COMMIT_SHORT}*) ;;
          *)
            echo "[reload] try ${i}: runtime commit=${runtime_commit} != disk ${DISK_COMMIT_SHORT}"
            sleep 2
            continue
            ;;
        esac
        ;;
    esac
  fi

  echo "[reload] health=200 after ${i} tries"
  echo "[reload] new_serve_pid=${new_pid} runtime_version=${runtime_version} runtime_commit=${runtime_commit:-?} runtime_pid=${runtime_pid:-?}"
  echo "[reload] disk_VERSION=${DISK_VERSION} disk_commit=${DISK_COMMIT_SHORT} mode=${RESTART_MODE}"
  ok=1
  break
done

if [ "$ok" != "1" ]; then
  echo "[reload] FAIL: process/runtime not switched (old_pid=${OLD_PID:-none} new_pid=$(first_pid) health may still be old)"
  echo "[reload] disk_VERSION=${DISK_VERSION} (disk alone is NOT success proof)"
  exit 1
fi

# 额外：若旧 PID 仍在，失败
if [ -n "${OLD_PID}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
  echo "[reload] FAIL: old serve pid ${OLD_PID} still alive"
  exit 1
fi

exit 0
