# MADR-0023 · 单会话 cookie `kanban_sid`（2.6.0）

- **状态**：已采纳（2026-07-25）
- **背景**：历史双 cookie `kanban_session`（管理）/ `kanban_view`（看端）+ 互清；2.5.0 已统一登录门面。
- **决策**：
  1. 唯一写入 cookie 名：**`kanban_sid`**
  2. 身份解析唯一入口：`session_ctx.resolve_session` → `AccountContext`
  3. 权限只看账号表 + `authz`（不看 cookie 名）
  4. 旧 cookie **兼容读 21 天**（锚点 `数据/session_legacy_compat_since.txt`），命中则静默升级写 sid
  5. 退出：清 `kanban_sid` + 两旧名（path=/、HttpOnly、SameSite=lax）
- **属性**：HttpOnly + SameSite=Lax；**不**硬开 Secure（外网仍 HTTP:8001）
- **参考**：
  - [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
  - [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- **后果**：测试与前端 401 按 sid；兼容窗外仅 sid 有效
- **编号说明**：`docs/madr/0022_*` 已占用（金额分整数）；本决策为 **0023**
