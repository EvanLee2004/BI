#!/usr/bin/env bash
# 3.7.3 标准发版入口：强制备份 + 候选端口预热 + 切流 + runtime 门闸
#
# 流程：
#   1) 业务库备份（P1-03，不可关生产）
#   2) 可选 git pull --ff-only
#   3) 候选预热：同目录新代码 KANBAN_PORT=8019 起旁路进程，health 对齐 version/commit
#      - 失败：杀候选；若已 pull 则 git reset --hard 回 prev；主 :8018 不动
#   4) 切流：
#      默认 warm：reload 主进程（systemctl）后杀候选
#      --nginx-cutover：upstream→8019 → reload 主 → upstream→8018 → 杀候选（近零断流）
#   5) 总闸 declare_publish_success
#
# 用法（生产机）：
#   bash deploy/linux/publish_kanban.sh --pull
#   bash deploy/linux/publish_kanban.sh --pull --nginx-cutover
#   bash deploy/linux/publish_kanban.sh --no-candidate   # 退回 3.7.0 半原子（仅 reload）
# 环境：KANBAN_SKIP_BACKUP=1 仅测结构，禁止生产
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

DO_PULL=0
USE_CANDIDATE=1
NGINX_CUTOVER=0
for arg in "$@"; do
  case "$arg" in
    --pull) DO_PULL=1 ;;
    --no-candidate) USE_CANDIDATE=0 ;;
    --nginx-cutover) NGINX_CUTOVER=1; USE_CANDIDATE=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

PRIMARY_PORT="${KANBAN_PRIMARY_PORT:-8018}"
CANDIDATE_PORT="${KANBAN_CANDIDATE_PORT:-8019}"
HEALTH_PRIMARY="${KANBAN_HEALTH_URL:-http://127.0.0.1:${PRIMARY_PORT}/api/v1/health}"
HEALTH_CANDIDATE="http://127.0.0.1:${CANDIDATE_PORT}/api/v1/health"
UPSTREAM_INC="$ROOT/deploy/linux/kanban_upstream.inc"
PY_BIN="python3"
[ -x "$ROOT/.venv/bin/python" ] && PY_BIN="$ROOT/.venv/bin/python"

DISK_VERSION=""
[ -f "$ROOT/VERSION" ] && DISK_VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
DISK_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
DISK_COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
PREV_COMMIT="$DISK_COMMIT"

echo "[publish] root=$ROOT $(date '+%Y-%m-%d %H:%M:%S')"
echo "[publish] disk_VERSION=${DISK_VERSION:-?} disk_commit=${DISK_COMMIT_SHORT:-?}"
echo "[publish] mode candidate=${USE_CANDIDATE} nginx_cutover=${NGINX_CUTOVER} primary=${PRIMARY_PORT} cand=${CANDIDATE_PORT}"

# --- helpers ---
kill_port_listeners() {
  local port="$1"
  # 仅杀监听该端口的 python/run.py（候选），不误杀无关
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
  # 兜底：按命令行端口环境
  ps -eo pid=,cmd= | awk -v p="$port" '
    /run\.py --serve/ && $0 ~ ("KANBAN_PORT=" p) { print $1 }
  ' | while read -r pid; do
    [ -n "$pid" ] || continue
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1
}

write_upstream() {
  local port="$1"
  ROOT="$ROOT" PY="$PY_BIN" PORT="$port" INC="$UPSTREAM_INC" "$PY_BIN" - <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
from publish_bluegreen import render_upstream_conf
port = int(os.environ["PORT"])
path = os.environ["INC"]
text = render_upstream_conf(port)
with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print(path, "port", port)
PY
}

nginx_reload_safe() {
  if sudo -n nginx -t >/dev/null 2>&1; then
    sudo -n nginx -t
    sudo -n systemctl reload nginx
    echo "[publish] nginx reloaded (passwordless)"
    return 0
  fi
  if sudo nginx -t >/dev/null 2>&1; then
    sudo nginx -t
    sudo systemctl reload nginx
    echo "[publish] nginx reloaded (sudo)"
    return 0
  fi
  echo "[publish] WARN: cannot nginx -t/reload (no sudo); skip cutover nginx steps"
  return 1
}

probe_health() {
  # args: url → sets _H_CODE _H_BODY and prints via python runtime fields to stdout as lines
  local url="$1"
  _H_BODY="$(curl -sS -m 5 "$url" 2>/dev/null || true)"
  _H_CODE="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
  printf '%s' "$_H_BODY" | ROOT="$ROOT" CODE="$_H_CODE" "$PY_BIN" - <<'PY'
import json, os, sys
body = sys.stdin.read()
code = os.environ.get("CODE") or "000"
try:
    d = json.loads(body) if body else {}
except Exception:
    d = {}
m = d.get("metrics") or {}
print(code)
print(m.get("version") or d.get("version") or "")
print(m.get("git_commit") or d.get("git_commit") or "")
print(m.get("pid") or d.get("pid") or "")
PY
}

candidate_ok_check() {
  local url="$1"
  local out
  out="$(probe_health "$url")"
  local code ver commit pid
  code="$(printf '%s\n' "$out" | sed -n '1p')"
  ver="$(printf '%s\n' "$out" | sed -n '2p')"
  commit="$(printf '%s\n' "$out" | sed -n '3p')"
  pid="$(printf '%s\n' "$out" | sed -n '4p')"
  ROOT="$ROOT" PY="$PY_BIN" CODE="$code" VER="$ver" CM="$commit" PID="$pid" \
  DV="$DISK_VERSION" DC="$DISK_COMMIT" "$PY_BIN" - <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
from publish_bluegreen import candidate_health_ok
ok, reason = candidate_health_ok(
    health_code=os.environ.get("CODE") or "000",
    runtime_version=os.environ.get("VER"),
    disk_version=os.environ.get("DV"),
    runtime_commit=os.environ.get("CM"),
    disk_commit=os.environ.get("DC"),
    runtime_pid=os.environ.get("PID"),
)
print("1" if ok else "0")
print(reason)
print(os.environ.get("VER") or "")
print(os.environ.get("CM") or "")
print(os.environ.get("PID") or "")
PY
}

# --- P1-03: 强制业务库备份 ---
BACKUP_PATH=""
BACKUP_SHA=""
MANIFEST_PATH=""
if [ "${KANBAN_SKIP_BACKUP:-0}" = "1" ]; then
  echo "[publish] WARN KANBAN_SKIP_BACKUP=1 — 禁止生产使用"
  BACKUP_OK=0
else
  DB_PATH="$ROOT/数据/看板.db"
  BAK_DIR="$ROOT/数据/备份"
  if [ ! -f "$DB_PATH" ]; then
    echo "[publish] FAIL: missing 数据/看板.db — 无库不可发版"
    exit 2
  fi
  mkdir -p "$BAK_DIR"
  BACKUP_JSON="$(
    ROOT="$ROOT" PY="$PY_BIN" DV="$DISK_VERSION" DC="$DISK_COMMIT" \
    "$PY_BIN" - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
from db_backup import backup_sqlite
meta = backup_sqlite(
    os.path.join(os.environ["ROOT"], "数据", "看板.db"),
    os.path.join(os.environ["ROOT"], "数据", "备份"),
    version=os.environ.get("DV") or "",
    commit=os.environ.get("DC") or "",
    prefix="看板_pre_publish",
)
print(json.dumps(meta, ensure_ascii=False))
PY
  )" || {
    echo "[publish] FAIL: backup_sqlite failed"
    exit 3
  }
  BACKUP_OK_JSON="$(
    ROOT="$ROOT" PY="$PY_BIN" META="$BACKUP_JSON" "$PY_BIN" - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
from publish_preflight import require_backup_meta
meta = json.loads(os.environ["META"])
ok, reason = require_backup_meta(meta)
print("1" if ok else "0")
print(reason)
print(meta.get("backup_path") or "")
print(meta.get("backup_sha256") or "")
print(meta.get("manifest_path") or "")
PY
  )"
  b_ok="$(printf '%s\n' "$BACKUP_OK_JSON" | sed -n '1p')"
  b_reason="$(printf '%s\n' "$BACKUP_OK_JSON" | sed -n '2p')"
  BACKUP_PATH="$(printf '%s\n' "$BACKUP_OK_JSON" | sed -n '3p')"
  BACKUP_SHA="$(printf '%s\n' "$BACKUP_OK_JSON" | sed -n '4p')"
  MANIFEST_PATH="$(printf '%s\n' "$BACKUP_OK_JSON" | sed -n '5p')"
  if [ "$b_ok" != "1" ]; then
    echo "[publish] FAIL: backup gate: $b_reason"
    exit 3
  fi
  echo "[publish] backup_ok path=$BACKUP_PATH sha256=${BACKUP_SHA:0:16}… manifest=$MANIFEST_PATH"
  BACKUP_OK=1
fi

# --- 可选 pull ---
PULLED=0
if [ "$DO_PULL" = "1" ]; then
  PREV_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  echo "[publish] git pull --ff-only origin main (prev=${PREV_COMMIT:0:12})"
  git -C "$ROOT" fetch origin main
  git -C "$ROOT" pull --ff-only origin main
  PULLED=1
  DISK_VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION" 2>/dev/null || true)"
  DISK_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  DISK_COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  echo "[publish] after pull disk_VERSION=$DISK_VERSION disk_commit=$DISK_COMMIT_SHORT"
fi

CAND_PID=""
cleanup_candidate() {
  if [ -n "${CAND_PID}" ] && kill -0 "$CAND_PID" 2>/dev/null; then
    kill -TERM "$CAND_PID" 2>/dev/null || true
    sleep 1
    kill -KILL "$CAND_PID" 2>/dev/null || true
  fi
  kill_port_listeners "$CANDIDATE_PORT"
}

abort_after_candidate_fail() {
  local reason="$1"
  echo "[publish] candidate FAIL: $reason"
  cleanup_candidate
  if [ "$PULLED" = "1" ] && [ -n "${PREV_COMMIT}" ]; then
    echo "[publish] reset --hard to prev ${PREV_COMMIT:0:12} (primary still old process)"
    git -C "$ROOT" reset --hard "$PREV_COMMIT" || true
  fi
  # ensure upstream back to primary
  write_upstream "$PRIMARY_PORT" || true
  exit 6
}

# --- 候选预热 ---
if [ "$USE_CANDIDATE" = "1" ]; then
  echo "[publish] starting candidate on :${CANDIDATE_PORT}"
  cleanup_candidate
  # 旁路：不走 start_with_rollback（避免抢 systemd 语义）；只验证新代码能起 + health 对齐
  (
    cd "$ROOT"
    export KANBAN_SERVER_HOST=127.0.0.1
    export KANBAN_SERVE_STATIC=0
    export KANBAN_PORT="$CANDIDATE_PORT"
    export KANBAN_CANDIDATE=1
    # 减少与主进程争用：候选不跑全量 boot 刷新若环境允许——仍走正常 serve，靠 health 判定
    exec env PYTHONPATH=src "$PY_BIN" run.py --serve
  ) >"$ROOT/数据/日志/candidate_publish.log" 2>&1 &
  CAND_PID=$!
  echo "[publish] candidate pid=$CAND_PID log=数据/日志/candidate_publish.log"

  CAND_READY=0
  CAND_REASON="timeout"
  for i in $(seq 1 90); do
    if ! kill -0 "$CAND_PID" 2>/dev/null; then
      CAND_REASON="candidate_exited"
      break
    fi
    chk="$(candidate_ok_check "$HEALTH_CANDIDATE" || true)"
    cok="$(printf '%s\n' "$chk" | sed -n '1p')"
    creason="$(printf '%s\n' "$chk" | sed -n '2p')"
    if [ "$cok" = "1" ]; then
      CAND_READY=1
      CAND_REASON="ok"
      echo "[publish] candidate health ok after ${i} tries reason=$creason"
      break
    fi
    sleep 2
  done
  if [ "$CAND_READY" != "1" ]; then
    abort_after_candidate_fail "${CAND_REASON}"
  fi
else
  echo "[publish] --no-candidate: skip warm-up"
fi

# --- 切流 ---
if [ "$USE_CANDIDATE" = "1" ] && [ "$NGINX_CUTOVER" = "1" ]; then
  echo "[publish] nginx cutover: upstream → ${CANDIDATE_PORT}"
  write_upstream "$CANDIDATE_PORT"
  if ! nginx_reload_safe; then
    echo "[publish] nginx cutover unavailable → fall back warm reload"
    NGINX_CUTOVER=0
    write_upstream "$PRIMARY_PORT" || true
  fi
fi

if ! bash "$ROOT/deploy/linux/reload_kanban.sh"; then
  echo "[publish] FAIL: reload_kanban.sh non-zero"
  if [ "$NGINX_CUTOVER" = "1" ]; then
    write_upstream "$PRIMARY_PORT" || true
    nginx_reload_safe || true
  fi
  cleanup_candidate
  echo "[publish] rollback hint: git -C $ROOT reset --hard ${PREV_COMMIT:0:12}; 备份 $BACKUP_PATH"
  exit 4
fi

if [ "$USE_CANDIDATE" = "1" ] && [ "$NGINX_CUTOVER" = "1" ]; then
  echo "[publish] nginx cutover: upstream → ${PRIMARY_PORT}"
  write_upstream "$PRIMARY_PORT"
  nginx_reload_safe || true
fi

cleanup_candidate

# --- 再读 health，publish_preflight 总闸 ---
body="$(curl -sS -m 5 "$HEALTH_PRIMARY" 2>/dev/null || true)"
code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$HEALTH_PRIMARY" 2>/dev/null || echo 000)"
eval "$(
  ROOT="$ROOT" BODY="$body" CODE="$code" DV="$DISK_VERSION" DC="$DISK_COMMIT" BOK="${BACKUP_OK:-0}" \
  "$PY_BIN" - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
from publish_preflight import declare_publish_success
from reload_verify import parse_health_metrics
m = parse_health_metrics(os.environ.get("BODY") or "")
ok, reason = declare_publish_success(
    health_code=os.environ.get("CODE") or "000",
    runtime_version=str(m.get("version") or ""),
    disk_version=os.environ.get("DV") or "",
    runtime_commit=str(m.get("git_commit") or ""),
    disk_commit=os.environ.get("DC") or "",
    runtime_pid=m.get("pid") or "",
    backup_ok=os.environ.get("BOK") == "1",
    process_switch_ok=True,
)
print(f"export PUB_OK={'1' if ok else '0'}")
print(f"export PUB_REASON={reason!r}")
print(f"export RT_VER={str(m.get('version') or '')!r}")
print(f"export RT_COMMIT={str(m.get('git_commit') or '')!r}")
print(f"export RT_PID={str(m.get('pid') or '')!r}")
PY
)"

if [ "${PUB_OK:-0}" != "1" ]; then
  echo "[publish] FAIL: gate reason=${PUB_REASON:-?} health=$code runtime_version=${RT_VER:-?} commit=${RT_COMMIT:-?} pid=${RT_PID:-?}"
  echo "[publish] disk_VERSION=$DISK_VERSION disk_commit=$DISK_COMMIT_SHORT backup=$BACKUP_PATH"
  exit 5
fi

echo "[publish] SUCCESS"
echo "[publish] runtime_version=$RT_VER runtime_commit=${RT_COMMIT:0:12} runtime_pid=$RT_PID health=$code"
echo "[publish] disk_VERSION=$DISK_VERSION disk_commit=$DISK_COMMIT_SHORT"
echo "[publish] backup_path=$BACKUP_PATH"
echo "[publish] bluegreen candidate_used=${USE_CANDIDATE} nginx_cutover=${NGINX_CUTOVER}"
exit 0
