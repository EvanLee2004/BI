#!/usr/bin/env bash
# 同步 Linux cron 哨兵段 kanban-schedule（任务书60）。
# 每日刷新已迁入服务进程 ScheduleLoop（serve 内 daemon），本脚本**不再**注册
# run.py --scheduled；重跑本脚本用于清掉旧机器上的刷新 cron 行。
# 健康检查 / 备份等其它 cron 不在本哨兵内，绝不动。
#
# 用法：在程序根目录执行  bash deploy/linux/register_schedule.sh
# 管理端「设置」保存时间点也会 best-effort 同步本哨兵段；失败再跑本脚本。
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# 解释器：优先 venv（系统 python3 建，MADR-0010）；勿写死带小版本号的解释器路径
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi

# 必须走 loaders.load_config（F-02），不可直读 config.json（时间点仅写入注释备忘）
TIMES="$("$PY" -c "import sys;sys.path.insert(0,'src');import loaders;c=loaders.load_config();ts=c.get('schedule_times') or [c.get('schedule_time') or '09:30'];print(' '.join(ts))")"
if [ -z "${TIMES// }" ]; then
  TIMES="09:30"
fi

# 哨兵段：绝不动用户其他 cron 行；段内无 --scheduled 命令
BEGIN="# BEGIN kanban-schedule"
END="# END kanban-schedule"

NEW_BLOCK="${BEGIN}
# managed by 看板正式程序 register_schedule / _linux_sync_schedule — do not edit by hand
# 任务书60：每日刷新已迁入服务进程 ScheduleLoop（serve 内 daemon），
# 本段故意无命令；当前配置时间点仅作备忘：${TIMES}
# 勿再添加 run.py --scheduled（独立进程不写 serve 内存 _state）。
${END}"

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

echo "[完成] 已同步 cron 哨兵段 kanban-schedule（无 --scheduled；刷新=ScheduleLoop）。"
echo "       配置时间点备忘：${TIMES}"
echo "       查看：crontab -l | sed -n '/BEGIN kanban-schedule/,/END kanban-schedule/p'"
