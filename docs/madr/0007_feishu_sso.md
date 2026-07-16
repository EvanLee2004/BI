# MADR-0007：飞书 SSO 骨架（未配置零行为）

- **状态**：Accepted（骨架）· 2026-07-17 · 任务书46·阶段1
- **背景**：内网看板需预留企业飞书统一登录；凭据与联调排期未定。
- **决策**：
  1. 新增 `src/sso_feishu.py`：authorize URL / 换 token / 用户映射接口骨架。
  2. 配置键 `feishu_sso.{app_id,app_secret,redirect_uri}`（或扁平 `feishu_sso_*`）；**三项缺一则完全禁用**，现有账号密码登录零变化。
  3. 不做真实联调；部署接入步骤见下文「待明昊」。
- **后果**：生产开启前须申请飞书应用、配置回调、账号映射规则；否则保持密码登录。
- **待明昊**：申请 app_id/app_secret、确定 redirect_uri（如 `https://看板域/api/sso/feishu/callback`）、映射字段（工号/手机/邮箱）。
