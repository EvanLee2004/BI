# FIX WAVE 执行手册 · 单 worktree 一次收口

> **给执行 Agent 的 SSOT**：本文件在本 worktree 根目录。  
> **基线**：`c02ba6dd513d59981c7988e860a4f36a176b76cf`（3.7.16）  
> **完美定义**：下表「必修」全关 + 最终门禁三码全 0 + 无 hold 被偷偷改掉 + 无完整 audit 漏洞包入库。  
> **hold 永不修**：明文 HTTP、密码明文 MADR-0020、弱密码策略、单 worker、手填缺月业务黄。

每完成一 Phase：更新同目录 `FIX_WAVE_STATUS.md` 对应行 → `git commit`。

---

## 全局命令（复制即用）

```bash
# 环境（缺则装；勿提交 .venv / node_modules）
test -x .venv/bin/python || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt ruff
test -d frontend/node_modules || (cd frontend && npm ci)

# 门禁（禁止 tail/head 判绿）
npm --prefix frontend run typecheck; echo TYPECHECK:$?
npm --prefix frontend run build; echo BUILD:$?
KANBAN_OFFLINE=1 sh tests/run_verify.sh; echo VERIFY:$?
```

**最终必须 TYPECHECK=0 BUILD=0 VERIFY=0。** 中途 Phase 至少跑相关单测；Phase 2/5 后建议全量 verify。

---

## Phase 清单与 DoD

### P1 · 前端隔离与 UX 默认

| ID | 做什么 | 关键文件 |
|----|--------|----------|
| FE-001 | scope/账号切换开始即 `clearDaily`；失败不留旧 daily；防过期响应 | `frontend/src/stores/cockpit.ts` + 测试 |
| FE-003 | session 失败时顶栏默认收紧（勿默认 admin） | `frontend/src/components/TopBarActions.vue` |
| FE-002 | F-2 守卫覆盖图表 TS 或色入 token | `tests/test_frontend_arch_guards.py`、chart-fx 等 |

**DoD**：新测红→绿；整体→BU / BU→整体 daily 清空；typecheck 0。  
**commit**：`fix(fe): clear daily dual across scopes and harden chrome defaults`

### P2 · DB / 写路径诚实

| ID | 做什么 | 关键文件 |
|----|--------|----------|
| BE-001 | rebuild + adj 重放同一原子事务 | `src/db_write.py`, `src/ingest/adjust.py`, `src/ingest/__init__.py` |
| BE-002 | 已写库后 recompute 失败 ≠ 409 忙 | `src/routes/manual.py` + tests |
| BE-006 | 在线 restore 安全（拒绝或强制停服） | `src/ingest/archive.py`, Runbook, tests |
| BE-003 | BU 配置写锁语义诚实 | `src/routes/config_api.py` |
| BE-004 | settings/账号与刷新竞态最小处理 | config/auth 写路径 |
| BE-005 | 关键读 snapshot 或可证明窗口 | `src/refresh_pipeline.py` / 读路径 |
| BE-007 | 日备降级策略/告警 | archive backup |
| BE-011 | ScheduleLoop 不可生产假 success | `src/schedule_loop.py` |

**DoD**：注入失败测覆盖 BE-001/002/006；VERIFY 建议 0。  
**commit**：`fix(be): atomic reapply, honest errors, safe restore, concurrency`

### P3 · 发版运维

| ID | 做什么 | 关键文件 |
|----|--------|----------|
| OPS-002 | 候选健康默认对齐 version/commit | `deploy/linux/publish_kanban.sh`, publish_bluegreen |
| OPS-001 | env 名与代码一致 | `kanban.service`, `src/server.py` |
| OPS-003 | declare_publish 勿假 PID OK | publish 脚本 |
| OPS-004 | reload kill 范围 | `reload_kanban.sh` + 文档 |
| OPS-005 | 回滚标记 vs 就绪 | `server.py` / start_with_rollback |
| TEST-005 | 测钉生产默认 | tests publish* |

**DoD**：静态测 + VERIFY 0。  
**commit**：`fix(ops): candidate gate align and publish safety`

### P4 · 权限安全（非 hold）

| ID | 做什么 | 关键文件 |
|----|--------|----------|
| AUTH-001 | 空态 bu_names 裁剪 | `src/routes/cockpit.py` |
| AUTH-002/003 | count/401 语义 | cockpit/authz |
| SEC-001 | CIFS 密码勿 argv | `src/ledger_cifs.py`, `deploy/linux/kanban-cifs-apply.sh` |
| SEC-002 | CSRF 死路径：签发或文档化 | csrf 相关 |
| SEC-003 | CSP 能收紧则收；否则注释残余 | security_headers |

**DoD**：BU 空态测；subprocess 无 --password；VERIFY 0。  
**commit**：`fix(sec): bu meta isolation and cifs secret channel`

### P5 · 财务与数据（敏感）

| ID | 做什么 | 关键文件 |
|----|--------|----------|
| FIN-001 | float 金额单一语义 + 守卫 | `src/money.py` |
| FIN-002 | 非法金额不静默当 0 | money, loaders |
| FIN-003 | 去税 1 分：脚注或统一 + 测 | `src/profit/tax_revenue.py` |
| FIN-004 | 100% 分摊尾差 | `src/profit/bu_alloc.py` |
| FIN-005 | Σpct>100 算账闸 | bu_alloc + 写路径 |
| FIN-006 | 台账 fallback 时效 | `src/ingest/fetch.py` 等 |
| FIN-007 | except pass → log | `src/ingest/__init__.py` |
| FIN-008 | adj 分/元边界 | `src/ingest/adjust.py` |
| FIN-009~012 | 安全清类型/注释债 | profit/core |

**硬门**：`regress_db_vs_files` 与金额相关测必须绿；数字变了必须证明是修 bug。  
**commit**：`fix(fin): money ingress, bad amounts, alloc edges, ingest honesty`

### P6 · 测试债

| ID | 做什么 |
|----|--------|
| TEST-001/002 | 写锁测真行为；禁源码假绿 |
| TEST-003 | 关键路径行为化（点杀高价值） |
| TEST-ENV | run_verify 防并行踩 数据/（锁或说明） |

**commit**：`test: eliminate false-green write-lock and gate races`

### P7 · 文档对齐（无漏洞利用细节）

对齐 VERSION / progress 施工指针 / AGENTS 版本摘要 / Runbook 与 P2–P3 行为。  
**禁止**提交完整 `docs/audit/20260805_全面审查_*` 包。  
**commit**：`docs: align version pointers after fix wave`

---

## 禁止清单（再念一遍）

- push / 部署 / 生产  
- 改 MADR-0020 明文密码、强制全站 HTTPS 当本波必须  
- 为绿删断言、改 golden 掩盖  
- 前端算金额  
- checkout 含完整审查的 tip 当工作区

---

## 完成后交付模板（必须输出）

```text
FINAL_HEAD: ...
COMMITS: (git log --oneline c02ba6d..HEAD)
TYPECHECK:0 BUILD:0 VERIFY:0
ID_STATUS_TABLE: FE-001=done ... HOLD-002=skipped_hold
CHROME: done|blocked:reason
RISKS: ...
```
