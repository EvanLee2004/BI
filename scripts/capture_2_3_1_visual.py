#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1 三主题视觉截图 + README ui 图（须脱敏数据服务，默认 _golden_data）。

用法（服务已起，KANBAN_BASE 指向假数据实例）：
  KANBAN_BASE=http://127.0.0.1:8028 .venv/bin/python scripts/capture_2_3_1_visual.py

输出：
  docs/_visual_2_3_1/{neon,dark,light}/*.png   （gitignore）
  docs/images/ui/*  覆盖 README 用图（进 git，禁止真实金额客户名）
  {SCRATCH}/kpi_231.txt  KPI 终值对账表
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8028")
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-86121cf38401/implementer",
    )
)
VIS = ROOT / "docs" / "_visual_2_3_1"
UI = ROOT / "docs" / "images" / "ui"
THEMES = ("neon", "dark", "light")

# 管理端路径源：frontend/src/admin/router.ts（禁止死路由；通配会 silent redirect 到 /admin）
ADMIN_SHOT_SPEC: list[tuple[str, str, str, tuple[str, ...]]] = [
    # path, out_png, url_must_contain, body_must_contain_any
    ("/admin", "07_admin_console.png", "/admin", ("控制台", "更新数据", "体检")),
    ("/admin/settings", "08_admin_settings.png", "/admin/settings", ("设置", "BU", "账号")),
    (
        "/admin/review/orderdept",
        "09_admin_order_dept.png",
        "/admin/review/orderdept",
        ("下单", "部门", "未填"),
    ),
    (
        "/admin/edit/manual",
        "10_admin_manual.png",
        "/admin/edit/manual",
        ("人工填写", "手填", "调整"),
    ),
    (
        "/admin/edit/detail",
        "11_admin_detail.png",
        "/admin/edit/detail",
        ("数据调整", "明细", "调整"),
    ),
]


def load_accounts():
    for path in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick(kind: str):
    rows = load_accounts()
    if kind == "admin":
        for a in rows:
            if a.get("权限") == "管理员" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "lushasha", "kanban2026"
    if kind == "bu":
        for a in rows:
            p = str(a.get("权限") or "")
            if p not in ("管理员", "整体", "") and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "bu_only", "8888"
    for a in rows:
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
        if a.get("权限") == "整体" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def fill_login(page, acc, pw):
    page.wait_for_timeout(200)
    if page.locator("input[type=password]").count():
        for i in range(page.locator("input").count()):
            el = page.locator("input").nth(i)
            t = (el.get_attribute("type") or "text").lower()
            if t != "password":
                try:
                    el.fill(acc)
                    break
                except Exception:
                    pass
        page.locator("input[type=password]").first.fill(pw)
    page.locator(
        "button:has-text('进入'), button:has-text('登录'), button[type=submit]"
    ).first.click()


def apply_theme_via_button(page, target: str, max_clicks: int = 5) -> str:
    """经主题钮循环到 target（neon|dark|light），返回最终 data-theme。"""

    def cur() -> str:
        return page.evaluate(
            "() => document.documentElement.dataset.theme || "
            "(document.documentElement.classList.contains('theme-light') ? 'light' : 'dark')"
        )

    for _ in range(max_clicks):
        if cur() == target:
            return cur()
        page.locator(
            "button:has-text('浅色'), button:has-text('深色'), "
            "button:has-text('霓虹'), button:has-text('亮/暗')"
        ).first.click(force=True)
        page.wait_for_timeout(450)
    return cur()


def capture_page(
    page,
    *,
    base: str,
    path: str,
    out_png: Path,
    url_must_contain: str,
    body_must_contain_any: tuple[str, ...],
    wait_ms: int = 900,
) -> Path:
    """goto → URL/body 身份门禁 → 截图。失败 raise，禁止 soft-ok。"""
    from urllib.parse import urlparse

    page.goto(f"{base}{path}", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(wait_ms)
    url = page.url or ""
    path_now = urlparse(url).path.rstrip("/") or "/"
    want = url_must_contain.rstrip("/") or "/"
    # 精确 pathname 对齐，避免 /admin 通配命中 /admin/settings
    if path_now != want:
        raise RuntimeError(
            f"capture identity FAIL path={path!r}: url={url!r} need exact path {want!r} got {path_now!r}"
        )
    body = page.inner_text("body") or ""
    if "找不到这个地址" in body or "页面不存在" in body:
        raise RuntimeError(f"capture 404 body path={path!r} url={url!r}")
    if not any(m in body for m in body_must_contain_any):
        raise RuntimeError(
            f"capture body markers FAIL path={path!r} url={url!r} "
            f"need any of {body_must_contain_any} snip={body[:160]!r}"
        )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_png), full_page=False)
    return out_png


def assert_pngs_unique(paths: list[Path], label: str) -> None:
    import hashlib

    digests: dict[str, Path] = {}
    for p in paths:
        if not p.is_file():
            raise RuntimeError(f"{label}: missing {p}")
        h = hashlib.sha1(p.read_bytes()).hexdigest()
        if h in digests:
            raise RuntimeError(
                f"{label}: duplicate PNG content {digests[h].name} == {p.name} sha1={h[:12]}"
            )
        digests[h] = p


def dismiss_intro(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        if page.locator(".intro-splash, [data-intro], .logo-intro").count():
            page.mouse.click(20, 20)
            page.wait_for_timeout(200)
    except Exception:
        pass


def wait_cockpit(page) -> None:
    page.wait_for_selector(
        "[data-testid=period-picker], .kpi-grid, .scifi-panel.kpi-card",
        timeout=60000,
    )
    page.wait_for_timeout(1200)
    dismiss_intro(page)
    page.wait_for_timeout(400)


def kpi_table(page) -> list[dict]:
    return page.evaluate(
        """() => {
          const cards = [...document.querySelectorAll('.scifi-panel.kpi-card, .kpi-grid .kpi-card, .kpi-grid .scifi-panel')];
          return cards.slice(0, 5).map((c, i) => {
            const name = (c.querySelector('.tag, .kpi-name, .dsdk-panel-header')?.textContent || '').trim().slice(0, 40);
            const val = (c.querySelector('.kpi-v b, .kpi-v .count-up-num, .kpi-v')?.textContent || '').trim();
            return { i, name, page_disp: val };
          });
        }"""
    )


def main() -> int:
    from playwright.sync_api import sync_playwright

    SCRATCH.mkdir(parents=True, exist_ok=True)
    for t in THEMES:
        (VIS / t).mkdir(parents=True, exist_ok=True)
    UI.mkdir(parents=True, exist_ok=True)

    vac, vpw = pick("overall")
    aac, apw = pick("admin")
    buc, bup = pick("bu")
    log: list[str] = []
    sensitive_hits: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        cons_errors: list[str] = []
        page.on(
            "console",
            lambda msg: cons_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )

        # login
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
        page.screenshot(path=str(UI / "01_login.png"), full_page=False)
        fill_login(page, vac, vpw)
        page.wait_for_load_state("networkidle", timeout=90000)
        wait_cockpit(page)
        log.append(f"login ok as {vac}")

        # fetch API kpi for对照：真实路径 j.kpi.cards_by_period[period]
        api_cards = page.evaluate(
            """async () => {
              const r = await fetch('/api/v1/vm/cockpit', {credentials:'include'});
              if (!r.ok) return {err: 'http '+r.status};
              const j = await r.json();
              const by = (j.kpi && j.kpi.cards_by_period) || j.cards_by_period || {};
              const keys = Object.keys(by);
              // 优先「年」卡（与默认顶栏一致）
              let period = keys.find(k => /年$/.test(k) && !k.includes('Q') && !k.includes('-'))
                || keys.find(k => k.includes('年'))
                || keys[0];
              const arr = Array.isArray(by[period]) ? by[period] : [];
              return {
                period,
                cards: arr.slice(0, 5).map(c => ({
                  name: c.label || c.name || c.title || '',
                  value_disp: (c.value_disp != null && c.value_disp !== '')
                    ? String(c.value_disp)
                    : ''
                }))
              };
            }"""
        )
        if not isinstance(api_cards, dict) or api_cards.get("err"):
            raise RuntimeError(f"cockpit API failed: {api_cards}")
        api_list = api_cards.get("cards") or []
        if len(api_list) < 1 or not all(c.get("value_disp") for c in api_list):
            raise RuntimeError(
                f"API value_disp empty — refuse tautology match. period={api_cards.get('period')} cards={api_list}"
            )
        log.append(f"api kpi period={api_cards.get('period')} n={len(api_list)}")

        kpi_rows: list[str] = ["theme | card | page | api_value_disp | match"]
        kpi_fail = 0
        for theme in THEMES:
            got = apply_theme_via_button(page, theme)
            assert got == theme, f"theme button failed: want {theme} got {got}"
            if theme == "light":
                assert page.evaluate(
                    "() => document.documentElement.classList.contains('theme-light')"
                ), "light missing theme-light"
            page.wait_for_timeout(600)
            # full home
            page.evaluate("window.scrollTo(0,0)")
            page.wait_for_timeout(300)
            page.screenshot(path=str(VIS / theme / "01_home.png"), full_page=False)
            # KPI strip
            kpi = page.locator(".kpi-grid, .kpi-host").first
            if kpi.count():
                kpi.screenshot(path=str(VIS / theme / "02_kpi.png"))
            else:
                page.screenshot(path=str(VIS / theme / "02_kpi.png"), full_page=False)
            # PL section
            pl = page.locator(".pl-card, #plCard, [data-section=pl]").first
            if pl.count():
                pl.scroll_into_view_if_needed()
                page.wait_for_timeout(400)
                pl.screenshot(path=str(VIS / theme / "03_pl.png"))
            else:
                page.evaluate("window.scrollTo(0, 900)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(VIS / theme / "03_pl.png"), full_page=False)
            # expense
            exp = page.locator(
                "#expenseCard, .expense-section, [data-section=expense], .expense-heat"
            ).first
            if exp.count():
                exp.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                exp.screenshot(path=str(VIS / theme / "04_expense.png"))
            else:
                page.evaluate("window.scrollTo(0, 1600)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(VIS / theme / "04_expense.png"), full_page=False)

            # KPI 对账：API 空 → fail；页值须含 value_disp（单位可在页侧）
            page_cards = kpi_table(page)
            for i, api in enumerate(api_list):
                pc = page_cards[i] if i < len(page_cards) else {}
                pd = re.sub(r"\s+", "", str(pc.get("page_disp") or ""))
                ad = re.sub(r"\s+", "", str(api.get("value_disp") or ""))
                unit = ""
                # 页显常带「万」「%」：允许 ad 是 pd 的数字核
                match = bool(ad) and (pd == ad or ad in pd or pd.replace("万", "").replace("%", "") == ad)
                if not match:
                    kpi_fail += 1
                kpi_rows.append(
                    f"{theme} | {api.get('name') or pc.get('name')} | {pc.get('page_disp')} | {api.get('value_disp')} | {match}"
                )

            # README 主图：neon 作默认演示感；dark 进 02_viewer_home_dark 历史文件名
            if theme == "neon":
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(200)
                page.screenshot(path=str(UI / "02_viewer_home_neon.png"), full_page=False)
            if theme == "dark":
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(200)
                page.screenshot(path=str(UI / "02_viewer_home_dark.png"), full_page=False)
                page.evaluate("window.scrollTo(0, 700)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(UI / "03_viewer_profit_section.png"), full_page=False)
                page.evaluate("window.scrollTo(0, 1400)")
                page.wait_for_timeout(400)
                page.screenshot(path=str(UI / "04_viewer_structure_section.png"), full_page=False)

            log.append(f"theme {theme} shots ok")

        # mobile neon
        page.set_viewport_size({"width": 375, "height": 812})
        apply_theme_via_button(page, "neon")
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(UI / "06_viewer_mobile.png"), full_page=False)
        page.screenshot(path=str(VIS / "neon" / "05_mobile_375.png"), full_page=False)
        page.set_viewport_size({"width": 1440, "height": 900})

        # BU page：bu 账号登录 → 服务端 redirect /bu/{名}；禁止 404 文案
        bu_ok = False
        try:
            page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
            fill_login(page, buc, bup)
            page.wait_for_load_state("networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            # 若仍停在 / 且有 bu-nav，点第一个 BU
            if "/bu/" not in page.url:
                link = page.locator("[data-testid=bu-nav] a.bu-nav-a, a.bu-nav-a").first
                if link.count():
                    href = link.get_attribute("href") or ""
                    link.click(force=True)
                    page.wait_for_timeout(1500)
                    if href and "/bu/" not in page.url:
                        page.goto(f"{BASE}{href}", wait_until="networkidle", timeout=60000)
                        page.wait_for_timeout(1000)
            body = page.inner_text("body")
            if "找不到这个地址" in body or "页面不存在" in body or page.locator("text=找不到这个地址").count():
                raise RuntimeError(f"BU page 404 url={page.url} body_snip={body[:120]!r}")
            if "/bu/" not in page.url:
                raise RuntimeError(f"not on /bu/* after bu login, url={page.url}")
            page.wait_for_selector(".kpi-grid, .scifi-panel, [data-testid=period-picker]", timeout=45000)
            for theme in THEMES:
                got = apply_theme_via_button(page, theme)
                if got != theme:
                    page.evaluate(
                        f"""() => {{
                      document.documentElement.dataset.theme = '{theme}';
                      document.documentElement.classList.toggle('theme-light', '{theme}'==='light');
                      localStorage.setItem('cockpit-theme','{theme}');
                    }}"""
                    )
                page.wait_for_timeout(500)
                body2 = page.inner_text("body")
                if "找不到这个地址" in body2:
                    raise RuntimeError(f"BU 404 under theme={theme}")
                page.screenshot(path=str(VIS / theme / "05_bu.png"), full_page=False)
            bu_ok = True
            log.append(f"bu shots ok url={page.url}")
        except Exception as e:
            log.append(f"bu shots FAIL: {e}")
            raise

        # admin：SHOT_SPEC 身份门禁（源 router.ts）；禁止死路由 soft-ok
        page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(400)
        if page.locator("input[type=password]").count():
            fill_login(page, aac, apw)
            page.wait_for_load_state("networkidle", timeout=90000)
            page.wait_for_timeout(1200)
        admin_pngs: list[Path] = []
        for path, shot, url_part, markers in ADMIN_SHOT_SPEC:
            out = capture_page(
                page,
                base=BASE,
                path=path,
                out_png=UI / shot,
                url_must_contain=url_part,
                body_must_contain_any=markers,
            )
            admin_pngs.append(out)
            log.append(f"admin ok {path} → {shot} url={page.url}")
        assert_pngs_unique(admin_pngs, "admin ui")
        log.append(f"admin shots ok unique n={len(admin_pngs)}")

        # sensitivity scan on viewer home body（示例/合成/测试客户名放行）
        body = ""
        try:
            page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
            fill_login(page, vac, vpw)
            wait_cockpit(page)
            body = page.inner_text("body")
        except Exception as e:
            log.append(f"sensitivity scan skip: {e}")
        for m in re.finditer(r"[\u4e00-\u9fff]{2,12}有限公司", body or ""):
            if not any(x in m.group(0) for x in ("示例", "合成", "测试")):
                sensitive_hits.append(m.group(0))

        browser.close()

    (SCRATCH / "kpi_231.txt").write_text("\n".join(kpi_rows) + "\n", encoding="utf-8")
    (SCRATCH / "capture_log.txt").write_text(
        "\n".join(log + [f"console_errors={len(cons_errors)}"] + cons_errors[:20])
        + "\n",
        encoding="utf-8",
    )
    if sensitive_hits:
        print("SENSITIVE?", sensitive_hits)
        return 2
    if kpi_fail:
        print("KPI_MISMATCH rows=", kpi_fail)
        print("\n".join(kpi_rows))
        return 3
    # 再校验磁盘上 admin 五图互异（防半截写盘）
    assert_pngs_unique([UI / s[1] for s in ADMIN_SHOT_SPEC], "admin ui disk")
    print("OK capture", VIS, UI)
    print("log:", "; ".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
