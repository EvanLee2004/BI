#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智云（明道云 HAP）自动登录：用账号密码换 md_pss_id 会话 cookie。

为什么用无头浏览器而非纯 HTTP：
- 登录接口 POST /wwwapi/Login/MDAccountLogin 的 password 字段是前端 RSA 加密后提交的
  （2026-07-10 实测截获）。纯 HTTP 登录需复刻其 RSA 公钥加密，脆且随前端升级易碎。
- 无头 Chromium 直接跑真实登录逻辑，前端怎么加密都不管，最稳。部署机装一次 chromium 即可。
- 登录页无验证码/滑块（2026-07-10 实测），账号密码两个框直登。

用法：
    from ingest import login_zhiyun
    token, account_id = login_zhiyun.login(zy_cfg)   # zy_cfg = 数据/智云配置.json 解析后的 dict
    # 成功返回 (md_pss_id, account_id或None)；失败抛 LoginError（调用方决定降级）
    # account_id 从登录后页面全局变量 md.global.Account.accountId 取（2026-07-10 实测可得），
    # 取到=换账号零配置（管理员端只填账号密码即可）；取不到返回 None、调用方沿用配置里的旧值。

契约：只负责"账号密码 → 会话"，不碰抓数、不写文件（写回配置由 fetch 层按需做）。
"""

from __future__ import annotations


class LoginError(RuntimeError):
    """登录失败（账号密码错、页面结构变、超时、无浏览器等）。"""


ACCOUNT_SEL = "#txtMobilePhone"  # 手机号/邮箱框（2026-07-10 实测 id）
PASSWORD_SEL = "input[type=password]"  # 密码框
LOGIN_BTN_SELECTORS = ["text=登 录", "text=登录", ".loginBtn"]
LOGIN_TIMEOUT_MS = 30000
POST_LOGIN_WAIT_MS = 6000


def login(zy: dict, headless: bool = True) -> tuple[str, str | None]:
    """账号密码登录智云，返回 (md_pss_id, account_id|None)。需要 zy 含 base_url/username/password。"""
    base = zy.get("base_url")
    user = zy.get("username")
    pwd = zy.get("password")
    if not (base and user and pwd):
        raise LoginError("智云配置缺 base_url/username/password，无法自动登录")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise LoginError(
            f"未安装 playwright（部署机需 pip install playwright + playwright install chromium）：{e}"
        ) from e

    try:
        with sync_playwright() as p:
            br = p.chromium.launch(headless=headless)
            try:
                ctx = br.new_context(ignore_https_errors=True)
                pg = ctx.new_page()
                pg.goto(base, wait_until="networkidle", timeout=LOGIN_TIMEOUT_MS)
                pg.fill(ACCOUNT_SEL, user)
                pg.fill(PASSWORD_SEL, pwd)
                if not _click_login(pg):
                    pg.keyboard.press("Enter")
                pg.wait_for_timeout(POST_LOGIN_WAIT_MS)
                token = _extract_token(ctx)
                if not token:
                    raise LoginError(f"登录后未取到 md_pss_id（当前地址 {pg.url}，可能账号密码错或需验证码）")
                return token, _extract_account_id(pg)
            finally:
                br.close()
    except LoginError:
        raise
    except Exception as e:  # noqa: BLE001
        raise LoginError(f"登录过程异常（{type(e).__name__}: {e}）") from e


def _click_login(pg) -> bool:
    for sel in LOGIN_BTN_SELECTORS:
        try:
            pg.click(sel, timeout=2500)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _extract_account_id(pg) -> str | None:
    """登录后从前端全局变量取当前账号 GUID（取不到返回 None，不影响登录成败）。"""
    try:
        return pg.evaluate("() => { try { return md.global.Account.accountId || null; } catch(e) { return null; } }")
    except Exception:  # noqa: BLE001
        return None


def _extract_token(ctx) -> str | None:
    for c in ctx.cookies():
        if c["name"] == "md_pss_id" and c.get("value"):
            return c["value"]
    return None
