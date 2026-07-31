#!/usr/bin/env bash
# 3.7.0 标准发版入口（半原子 · P1-02 + P1-03）
# 顺序：业务库备份（强制）→ 可选 ff-only pull → reload_kanban → 再门闸 → SUCCESS/FAIL
# 诚实：非蓝绿；无旁路端口预热；成功仅当 backup+version+commit+pid+health 全齐。
# 用法（生产机）：
#   bash deploy/linux/publish_kanban.sh              # 备份 + reload（已 pull 时）
#   bash deploy/linux/publish_kanban.sh --pull       # 备份 + git pull --ff-only + reload
# 环境：KANBAN_SKIP_BACKUP=1 仅测脚本结构时禁止用于生产
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

DO_PULL=0
for arg in "$@"; do
  case "$arg" in
    --pull) DO_PULL=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

HEALTH_URL="${KANBAN_HEALTH_URL:-http://127.0.0.1:8018/api/v1/health}"
PY_BIN="python3"
[ -x "$ROOT/.venv/bin/python" ] && PY_BIN="$ROOT/.venv/bin/python"

DISK_VERSION=""
[ -f "$ROOT/VERSION" ] && DISK_VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
DISK_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
DISK_COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"

echo "[publish] root=$ROOT $(date '+%Y-%m-%d %H:%M:%S')"
echo "[publish] disk_VERSION=${DISK_VERSION:-?} disk_commit=${DISK_COMMIT_SHORT:-?}"

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
if [ "$DO_PULL" = "1" ]; then
  echo "[publish] git pull --ff-only origin main"
  git -C "$ROOT" fetch origin main
  git -C "$ROOT" pull --ff-only origin main
  DISK_VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION" 2>/dev/null || true)"
  DISK_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  DISK_COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  echo "[publish] after pull disk_VERSION=$DISK_VERSION disk_commit=$DISK_COMMIT_SHORT"
fi

# --- reload（内部已有 process switch 门闸）---
if ! bash "$ROOT/deploy/linux/reload_kanban.sh"; then
  echo "[publish] FAIL: reload_kanban.sh non-zero"
  echo "[publish] rollback hint: git -C $ROOT log -1; 备份 $BACKUP_PATH"
  exit 4
fi

# --- 再读 health，publish_preflight 总闸 ---
body="$(curl -sS -m 5 "$HEALTH_URL" 2>/dev/null || true)"
code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
eval "$(
  ROOT="$ROOT" BODY="$body" CODE="$code" DV="$DISK_VERSION" DC="$DISK_COMMIT" BOK="$BACKUP_OK" \
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
    process_switch_ok=True,  # reload 已证明切换；此处再验 runtime 对齐
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
exit 0
