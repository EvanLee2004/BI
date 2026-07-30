# MADR-0026 · 密码哈希与禁止明文回显（3.6.0）

## Status
Accepted · supersedes MADR-0020（管理员可看明文）for product version ≥ 3.6.0.

## Context
3.5.0 调查确认明文口令、无 CSRF、缺安全头等 P0/P1。

## Decision
- 存储：PBKDF2-HMAC-SHA256（stdlib），格式 `pbkdf2_sha256$iter$salt$hash`
- 登录：常量时间校验；遗留明文在迁移前仍可验证
- 改密/重置：落盘哈希；重置 API 仅一次返回临时明文
- 账号列表 API：永不返回 password/hash
- CSRF：状态变更校验 Origin/Referer 同源
- 安全头：CSP / X-Content-Type-Options / X-Frame-Options / Referrer-Policy；HTTPS 时 HSTS

## Consequences
- 管理端 UI 不得依赖下发明文列
- 测试口令仍可用 seed 明文直至首次 set_password
