# MADR-0024 · 会话 TTL 统一 7 天

- **Status**: Accepted
- **Date**: 2026-08-10
- **Version**: 3.7.20

## Context

用户反馈登录后「很快又要输密码」。排查确认非 cookie 损坏，而是 `SESSION_TTL = 12 * 3600`（任务书63 过渡）且**无滑动续期**。

## Decision

- 唯一 SSOT：`app_state.SESSION_TTL = 7 * 24 * 3600`（604800s）。
- cookie `max_age`（`kanban_sid` + `csrf_token`）与 HMAC token `exp` 同源该常量。
- 管理端 / 整体 / BU **同一 TTL**；禁止双轨。
- **不做**滑动续期 / 「记住我」/ 改 cookie 名 / 改 CSRF Secure / 改账号明文契约。
- 改密 / 退出 / 密码版本 bump 踢会话保持。
- 上线：旧 12h token 自然过期；新登录即 7 天。

## Consequences

- 内网共享电脑会话更长：产品已接受；退出/改密仍可踢会话。
- 用户须**重登一次**后才拿到 7 天 cookie。

## Related

- MASTER 3.7.20；MADR-0020 缓解表同步「会话 7 天」；守卫 `tests/test_session_ttl_3_7_20.py`。
