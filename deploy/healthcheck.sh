#!/usr/bin/env bash
# 看板健康探测（54.8）
# 用法：
#   BASE=http://127.0.0.1:8018 bash deploy/healthcheck.sh
# 失败写 deploy/health_alerts.log（时间+原因），exit 1

set -u
BASE="${BASE:-http://127.0.0.1:8018}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 任务书60 后：cron 输出优先 数据/日志；兼容旧 deploy 路径
LOG_DIR="$ROOT/数据/日志"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="${HEALTH_ALERT_LOG:-$LOG_DIR/healthcheck_alerts.log}"
if [ ! -d "$(dirname "$LOG")" ]; then
  LOG="${HEALTH_ALERT_LOG:-$ROOT/deploy/health_alerts.log}"
fi
MAX_STALE_DAYS="${MAX_STALE_DAYS:-2}"
# 磁盘余量：低于该比例（默认 0.10=10%）告警；可用 DISK_FREE_MIN_RATIO 覆盖
DISK_FREE_MIN_RATIO="${DISK_FREE_MIN_RATIO:-0.10}"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 任务书64·D8：失败时尝试飞书 webhook（读 本地配置/config 合并；未配置则只写本地 log）
notify_feishu() {
  local reason="$1"
  python3 - <<PY 2>/dev/null || true
import json, sys
from pathlib import Path
root = Path(r"$ROOT")
sys.path.insert(0, str(root / "src"))
try:
    import loaders
    import notify
    cfg = loaders.load_config(root, strict=False)
    notify.maybe_alert_text(cfg, f"【经营看板健康检查失败】{reason}")
except Exception:
    pass
PY
}

alert() {
  local reason="$1"
  mkdir -p "$(dirname "$LOG")"
  echo "$(ts) ALERT $reason" >>"$LOG"
  echo "ALERT: $reason" >&2
  notify_feishu "$reason"
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

# 3) 数据新鲜度（2.6.3·B1）：只认 /api/health 的 built_at 业务时间戳
# 禁止用 看板.db mtime——看端明细/登录审计写会刷新 mtime，导致 data_stale 永不触发。
DATA_DIR="$ROOT/数据"
if [ ! -d "$DATA_DIR" ]; then
  DATA_DIR="$ROOT/_golden_data"
fi
stale_info="$(python3 - <<PY
import json, urllib.request, time
from datetime import datetime
base = r"$BASE"
max_days = int(r"$MAX_STALE_DAYS" or "2")
try:
    with urllib.request.urlopen(base + "/api/health", timeout=5) as r:
        body = json.loads(r.read().decode("utf-8", errors="replace"))
except Exception as e:
    print(f"health_unreachable err={type(e).__name__}")
    raise SystemExit(0)
built = (body.get("built_at") or body.get("run_time") or "").strip()
if not built:
    # 尚无发布态：不按 stale 红（冷启动/首次部署）；metrics.built_at 亦无
    m = body.get("metrics") or {}
    built = str(m.get("built_at") or "").strip()
if not built:
    print("no_built_at")
    raise SystemExit(0)
# 接受 "YYYY-MM-DD HH:MM:SS" 或 ISO
ts = None
for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
    try:
        ts = datetime.strptime(built[:19].replace("T", " ") if "T" in built[:19] else built[:19], fmt if fmt != "%Y-%m-%dT%H:%M:%S" else "%Y-%m-%d %H:%M:%S")
        break
    except ValueError:
        continue
if ts is None:
    try:
        ts = datetime.strptime(built[:10], "%Y-%m-%d")
    except ValueError:
        print(f"built_at_unparsed value={built!r}")
        raise SystemExit(0)
age_days = (time.time() - ts.timestamp()) / 86400.0
if age_days > max_days:
    print(f"data_stale age_days={age_days:.2f} max={max_days} built_at={built}")
else:
    print(f"ok age_days={age_days:.2f} built_at={built}")
PY
)"
case "$stale_info" in
  data_stale*)
    alert "$stale_info"
    ;;
  health_unreachable*)
    alert "$stale_info base=$BASE"
    ;;
esac

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

# 5) 磁盘余量（任务书64·D8）：数据目录所在盘低于阈值 → 红
disk_ratio="$(python3 - <<PY
import os, shutil
from pathlib import Path
p = Path(r"$DATA_DIR")
if not p.is_dir():
    p = Path(r"$ROOT")
try:
    u = shutil.disk_usage(str(p))
    print(f"{u.free / u.total:.6f}" if u.total else "1")
except Exception:
    print("1")
PY
)"
# bash 无浮点：用 python 比较
disk_bad="$(python3 - <<PY
r = float("$disk_ratio" or "1")
thr = float("$DISK_FREE_MIN_RATIO" or "0.10")
print("1" if r < thr else "0")
PY
)"
if [ "$disk_bad" = "1" ]; then
  alert "disk_free_low ratio=$disk_ratio min=$DISK_FREE_MIN_RATIO path=$DATA_DIR"
fi

echo "$(ts) OK base=$BASE login=200 home=$code2 data_age_ok fe_err_24h=${yellow_fe:-0} disk_free=$disk_ratio"
exit 0

