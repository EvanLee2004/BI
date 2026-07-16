#!/usr/bin/env bash
# 注册 Linux cron：每天在「合并配置」(config.json + 数据/本地配置.json) 的 schedule_times
# 每个时间点各跑一次 run.py --scheduled。
# 选 cron 而非 systemd timer 的理由：无需 root、多时间点一行一条最简（见 docs/madr/0001_cron_vs_timer.md）。
# 与 Windows 注册每日更新.bat 语义对齐；Windows 资产保留标 legacy。
#
# 用法：在程序根目录执行  bash deploy/linux/register_schedule.sh
# 管理端「设置」保存时间点也会 best-effort 同步 crontab 哨兵段；失败再跑本脚本。
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi

# 与 .bat 相同：必须走 loaders.load_config（F-02），不可直读 config.json
TIMES="$("$PY" -c "import sys;sys.path.insert(0,'src');import loaders;c=loaders.load_config();ts=c.get('schedule_times') or [c.get('schedule_time') or '09:30'];print(' '.join(ts))")"
if [ -z "${TIMES// }" ]; then
  TIMES="09:30"
fi

# 哨兵段：绝不动用户其他 cron 行
BEGIN="# BEGIN kanban-schedule"
END="# END kanban-schedule"
RUNPY="$ROOT/run.py"
# crontab 行：分 时 * * *  命令
LINES=""
for t in $TIMES; do
  HH="${t%%:*}"
  MM="${t##*:}"
  # 去前导零以免 cron 部分实现对 08 当八进制
  HH=$((10#$HH))
  MM=$((10#$MM))
  LINES="${LINES}${MM} ${HH} * * * \"${PY}\" \"${RUNPY}\" --scheduled
"
done

NEW_BLOCK="${BEGIN}
# managed by 看板正式程序 register_schedule / _linux_sync_schedule — do not edit by hand
${LINES}${END}"

# 读现有 crontab（无则空）
OLD="$(crontab -l 2>/dev/null || true)"
# 去掉旧哨兵段
STRIPPED="$(printf '%s\n' "$OLD" | awk -v b="$BEGIN" -v e="$END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
')"
# 拼回：保留其它行 + 新哨兵段
{
  printf '%s\n' "$STRIPPED" | sed '/^$/N;/^\n$/D'
  echo "$NEW_BLOCK"
} | sed '/^$/N;/^\n$/D' | crontab -

echo "[完成] 已按 ${TIMES} 注册 cron（哨兵段 kanban-schedule）。"
echo "       查看：crontab -l | sed -n '/BEGIN kanban-schedule/,/END kanban-schedule/p'"
