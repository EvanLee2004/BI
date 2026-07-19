#!/usr/bin/env bash
# 看板健康探测（54.8）
# 用法：
#   BASE=http://127.0.0.1:8018 bash deploy/healthcheck.sh
# 失败写 deploy/health_alerts.log（时间+原因），exit 1

set -u
BASE="${BASE:-http://127.0.0.1:8018}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${HEALTH_ALERT_LOG:-$ROOT/deploy/health_alerts.log}"
MAX_STALE_DAYS="${MAX_STALE_DAYS:-2}"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

alert() {
  local reason="$1"
  mkdir -p "$(dirname "$LOG")"
  echo "$(ts) ALERT $reason" >>"$LOG"
  echo "ALERT: $reason" >&2
  exit 1
}

# 1) 登录页 200
code="$(python3 - <<PY
import urllib.request
try:
    r=urllib.request.urlopen("$BASE/login", timeout=5)
    print(r.status)
except Exception as e:
    print(0)
PY
)"
if [ "$code" != "200" ]; then
  alert "login_page_not_200 base=$BASE code=$code"
fi

# 2) 首页可达：连接失败 code=0 必须告警；200/301/302 视为可达
code2="$(python3 - <<PY
import urllib.request
import urllib.error
try:
    r = urllib.request.urlopen("$BASE/", timeout=5)
    print(r.status)
except urllib.error.HTTPError as e:
    # 未跟随时可能拿到 3xx/4xx；3xx 仍算可达
    print(e.code)
except Exception:
    print(0)
PY
)"
if [ "$code2" = "0" ]; then
  alert "home_unreachable base=$BASE code=$code2"
fi
if [ "$code2" != "200" ] && [ "$code2" != "301" ] && [ "$code2" != "302" ] && [ "$code2" != "303" ] && [ "$code2" != "307" ] && [ "$code2" != "308" ]; then
  # 4xx/5xx 等非可达
  alert "home_not_ok base=$BASE code=$code2"
fi

# 3) 数据新鲜度：看板.db 或 data_dir 下最新 xlsx mtime
# 相对 ROOT；data_dir 默认 数据
DATA_DIR="$ROOT/数据"
if [ ! -d "$DATA_DIR" ]; then
  DATA_DIR="$ROOT/_golden_data"
fi
latest=0
if [ -f "$DATA_DIR/看板.db" ]; then
  latest=$(stat -f %m "$DATA_DIR/看板.db" 2>/dev/null || stat -c %Y "$DATA_DIR/看板.db" 2>/dev/null || echo 0)
fi
for f in "$DATA_DIR"/*.xlsx; do
  [ -f "$f" ] || continue
  m=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)
  if [ "$m" -gt "$latest" ]; then latest=$m; fi
done
now=$(date +%s)
if [ "$latest" -gt 0 ]; then
  age_days=$(( (now - latest) / 86400 ))
  if [ "$age_days" -gt "$MAX_STALE_DAYS" ]; then
    alert "data_stale age_days=$age_days max=$MAX_STALE_DAYS path=$DATA_DIR"
  fi
fi

# 4) 前端错误日志黄灯（B-5）：近 24h 有客户端错误 → YELLOW（不判红，exit 0 仍成功）
FE_ERR="$DATA_DIR/前端错误.log"
yellow_fe=0
if [ -f "$FE_ERR" ]; then
  # 用 python 解析 JSON 行时间戳，避免依赖 date -d 跨平台差异
  yellow_fe="$(python3 - <<PY
import json, time, os
path = r"$FE_ERR"
cutoff = time.time() - 24 * 3600
n = 0
try:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                ts = (o.get("ts") or "")[:19]
                t = time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) if len(ts) >= 19 else 0
                if t >= cutoff:
                    n += 1
            except Exception:
                pass
except OSError:
    n = 0
print(n)
PY
)"
fi
if [ "${yellow_fe:-0}" -gt 0 ] 2>/dev/null; then
  echo "$(ts) YELLOW frontend_errors_24h=$yellow_fe path=$FE_ERR" | tee -a "$LOG"
  echo "YELLOW: frontend_errors_24h=$yellow_fe" >&2
  # 黄灯不 exit 1；演示/巡检看 YELLOW 行即可
fi

echo "$(ts) OK base=$BASE login=200 home=$code2 data_age_ok fe_err_24h=${yellow_fe:-0}"
exit 0

