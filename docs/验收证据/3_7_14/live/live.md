# 3.7.14 本地 OFFLINE 活体记录

> 时间：2026-08-05 · 执行机 macOS worktree · `KANBAN_OFFLINE=1`  
> 方式：API / 单测直驱 + 结构断言（可代截图）

## L1 登录（HTTP · Cookie 无 Secure）

- **点了什么**：`POST /api/v1/login`（TestClient 纯 HTTP，无 X-Forwarded-Proto）  
- **看到什么**：200；`Set-Cookie` 含 `kanban_sid`、**无** `Secure`；随后 `GET /api/v1/session` 200  
- **证据**：`test_login_http_sets_cookie_without_secure` OK

## L2 整体导出鉴权

- **点了什么**：未登录 `GET /api/v1/export.html`；`no_export` 账号登录后同路径  
- **看到什么**：未登录 **401**；已登录无 cap **403**  
- **证据**：`Test005ExportAuthMatrix` OK

## L3 BU 导出

- **点了什么**：`bu_only` 账号 `GET /api/v1/export/bu/不存在线/html`  
- **看到什么**：**403**（非 401）  
- **证据**：`test_bu_user_forbidden_other_bu_403_not_401` OK

## L4 费用口径文案

- **点了什么**：读 `ExpenseSection` / ledger `caliber_note` 源与后端字段  
- **看到什么**：旁注区分饼/分摊 vs「业务BU」原始行  
- **证据**：`TestH20*` OK；`cockpit.py` caliber_note 文案

## L5 设置路径探测（API）

- **点了什么**：管理员 `GET /api/v1/admin/settings`（实现含 `ledger_path_exists`）  
- **看到什么**：字段 `ledger_path_exists: bool`；设置页展示「路径探测：存在可读/不存在」  
- **说明**：本机 OFFLINE fixture 路径可能 false；生产 gvfs 在线时 true（见 preflight）

## L6 前端竞态 / session 单飞

- **点了什么**：node 直驱 `fetchRace` / `sessionSingleflight` 纯函数  
- **看到什么**：旧世代 stale；并发 session 合并为 1 次 fetch；invalidate 后二次  
- **证据**：`test_audit_3_7_14_frontend.py` OK；`npm run typecheck` OK
