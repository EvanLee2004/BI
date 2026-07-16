#!/usr/bin/env bash
# 看门狗启动（Linux）：常驻运行经营罗盘服务，支持管理端「一键更新」后自动重启 + 坏版本自愈。
# 语义对齐根目录 看门狗启动.bat（Windows legacy 保留）：
#   - 退出码 42 = 一键更新后重启信号 → 用新代码重启，失败计数清零
#   - 非 42 且存在 .update_rollback → 自动 git reset --hard 回滚一次再起（只一次，删标记）
#   - 其它非 42：累计失败，连续 ≥5 次停下（配合 systemd StartLimitBurst）
# 用法：由 kanban.service ExecStart 调用；也可手动：bash deploy/linux/start_with_rollback.sh
# 不用 set -e：服务退出非 0 是常态；中文 echo 在部分 locale 下也不应打断循环
set -u
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi

FAILS=0
MAX_FAILS=5

while true; do
  echo "[看门狗] 启动服务 $(date '+%Y-%m-%d %H:%M:%S')"
  "$PY" run.py --serve
  CODE=$?

  if [ "${CODE}" -eq 42 ]; then
    echo "[看门狗] 收到更新后重启信号(42)，用新代码重启..."
    FAILS=0
    sleep 2
    continue
  fi

  # 非 42：异常退出。有回滚标记 = 更新后启动即崩 → 回滚一次
  if [ -f "${ROOT}/.update_rollback" ]; then
    PREV="$(tr -d '[:space:]' < "${ROOT}/.update_rollback" || true)"
    rm -f "${ROOT}/.update_rollback"
    # 变量一律 ${VAR}：macOS bash 3.2 对 $VAR 紧贴全角括号会误解析
    echo "[看门狗] 更新后启动异常(码=${CODE})，自动回滚到更新前版本 ${PREV} ..."
    # 飞书告警（未配置 webhook 则静默；失败不挡回滚）
    (cd "${ROOT}" && PYTHONPATH=src "${PY}" -c "from notify import alert_event; alert_event('rollback', 'exit=${CODE} prev=${PREV}')" ) 2>/dev/null || true
    if [ -n "${PREV}" ]; then
      if ! git -C "${ROOT}" reset --hard "${PREV}"; then
        echo "[看门狗] 回滚失败，请人工检查：git -C \"${ROOT}\" reset --hard ${PREV}"
        exit 1
      fi
    fi
    FAILS=0
    sleep 3
    continue
  fi

  FAILS=$((FAILS + 1))
  echo "[看门狗] 服务退出码=${CODE} (第 ${FAILS} 次异常退出)"
  if [ "${FAILS}" -ge "${MAX_FAILS}" ]; then
    echo "[看门狗] 连续异常退出过多，停止自动重启。"
    echo "        可能新版本有问题——请人工检查 journalctl -u kanban；需回滚可跑："
    echo "        git -C \"${ROOT}\" reset --hard HEAD~1 && sudo systemctl restart kanban"
    (cd "${ROOT}" && PYTHONPATH=src "${PY}" -c "from notify import alert_event; alert_event('boot_crash', 'fails=${FAILS} code=${CODE}')" ) 2>/dev/null || true
    exit 1
  fi
  sleep 3
done
