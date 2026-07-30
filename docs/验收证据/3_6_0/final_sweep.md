# G6 final_sweep · 3.6.0 候选收口

## 版本与门禁

- VERSION=3.6.0
- 基线：`ef90dc4d43a42656f99b3411112a5737014c460b`
- 离线门禁：`KANBAN_OFFLINE=1 sh tests/run_verify.sh` → EXIT:0 · runtime skip=0
- 证据：`gates/g6_full_gate.log`（及 g0/g1）

## 安全扫描摘要

| 工具 | 结果 | 路径 |
|---|---|---|
| ruff | All checks passed | security/ruff.txt |
| bandit | High=0；Medium 含历史 SQL/bind 噪音 | security/bandit.txt |
| npm audit | 2 moderate（echarts、element-plus）→ **P2-08 BLOCKED** | security/npm_audit.txt |
| pip-audit | 工具未装（记录） | security/pip_audit.txt |
| gitleaks | 扫到本地 `数据/` 物化 fixture（gitignore，不进库）；无新增 git 秘密 | security/gitleaks.txt |

## 活体

- playwright chromium：**OK**（`live/browser_env.txt`）
- manifest：5 条完整字段（`live/manifest.json`）；像素截图以结构+单元为主，诚实标注

## 架构

- server.py 薄门面（boot_lifecycle 拆出）
- keyCustomersAxis 纯函数；dist 已重建

## 控制卡

- state=REVIEW_READY
- 见控制卡文件与 00_总控勾选.md

## 声明

未 push、未部署、未改生产数据。非 VERIFIED。
