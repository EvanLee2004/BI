#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次级性能检查（54.8 资产化 · 不进 run_verify 日常路径）。

用法（服务已起 8018，建议 KANBAN_OFFLINE=1 + 合成数据）：
  KANBAN_BASE=http://127.0.0.1:8018 .venv/bin/python tests/perf_check.py

环境变量：
  KANBAN_BASE  默认 http://127.0.0.1:8018
  PERF_SKIP_LONG=1  跳过 10 分钟长会话（默认跳过，避免卡住 CI）

输出：指标|阈值|实测|结论 表；任一项「硬阈值」失败则 exit 1。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
SKIP_LONG = os.environ.get("PERF_SKIP_LONG", "1") == "1"


def load_accounts():
    # 优先本机 数据/（部署/开发机真实口令）；golden 仅兜底
    for p in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick(kind: str):
    rows = load_accounts()
    if kind == "admin":
        for a in rows:
            if a.get("权限") == "管理员" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
        return "lushasha", "kanban2026"
    for a in rows:
        if a.get("权限") in ("整体",) and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    for a in rows:
        if a.get("账号") in ("overall", "123") and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "overall", "8888"


def fill_login(page, acc, pw, enter=False):
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
    btn = "进入" if enter else "登录"
    page.locator(
        f"button:has-text('{btn}'), button:has-text('登录'), button:has-text('进入'), button[type=submit]"
    ).first.click()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("SKIP: playwright 不可用:", e)
        return 2

    rows: list[dict] = []
    hard_fail = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 首屏：登录到 idle
        vac, vpw = pick("overall")
        t0 = time.perf_counter()
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90000)
        fill_login(page, vac, vpw, enter=False)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        ms = (time.perf_counter() - t0) * 1000
        ok = ms < 3000
        hard_fail = hard_fail or not ok
        rows.append(
            {
                "指标": "看端登录→idle",
                "阈值": "<3000ms",
                "实测": f"{ms:.0f}ms",
                "结论": "达标" if ok else "超标",
            }
        )

        # 交互：轻量滚动（避免点隐藏 <option> 超时）
        t0 = time.perf_counter()
        page.evaluate("window.scrollTo(0, 400)")
        page.wait_for_timeout(150)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(100)
        ms = (time.perf_counter() - t0) * 1000
        rows.append(
            {
                "指标": "首页滚动往返",
                "阈值": "软测 <600ms",
                "实测": f"{ms:.0f}ms",
                "结论": "记录" if ms < 600 else "偏慢(记录)",
            }
        )

        # 管理端首屏
        aacc, apw = pick("admin")
        t0 = time.perf_counter()
        page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
        fill_login(page, aacc, apw, enter=True)
        page.wait_for_load_state("networkidle")
        ms = (time.perf_counter() - t0) * 1000
        ok = ms < 3000
        hard_fail = hard_fail or not ok
        rows.append(
            {
                "指标": "管理端登录→idle",
                "阈值": "<3000ms",
                "实测": f"{ms:.0f}ms",
                "结论": "达标" if ok else "超标",
            }
        )

        # orderdept 打开（Vue SPA：等 hash/history 路由 + 工具条）
        t0 = time.perf_counter()
        page.goto(f"{BASE}/admin/review/orderdept", wait_until="networkidle", timeout=90000)
        page.wait_for_load_state("networkidle")
        # 兼容：.toolbar（OrderDeptView）或 el-table / admin 布局
        page.wait_for_selector(".toolbar, .el-table, .admin-layout, #app", timeout=30000)
        # 若仍在登录页则再填一次
        if page.locator("input[type=password]").count() and page.locator(".toolbar").count() == 0:
            fill_login(page, aacc, apw, enter=True)
            page.wait_for_load_state("networkidle")
            page.goto(f"{BASE}/admin/review/orderdept", wait_until="networkidle", timeout=90000)
            page.wait_for_selector(".toolbar, .el-table", timeout=30000)
        ms = (time.perf_counter() - t0) * 1000
        ok = ms < 2000
        hard_fail = hard_fail or not ok
        rows.append(
            {
                "指标": "下单未填部门打开",
                "阈值": "<2000ms",
                "实测": f"{ms:.0f}ms",
                "结论": "达标" if ok else "超标",
            }
        )

        if SKIP_LONG:
            rows.append(
                {
                    "指标": "10分钟长会话内存",
                    "阈值": "增幅≤50%",
                    "实测": "SKIP (PERF_SKIP_LONG=1)",
                    "结论": "跳过",
                }
            )
        else:
            rows.append(
                {
                    "指标": "10分钟长会话内存",
                    "阈值": "增幅≤50%",
                    "实测": "未实现完整 CDP 堆采样",
                    "结论": "跳过",
                }
            )

        browser.close()

    # 打印表
    print("| 指标 | 阈值 | 实测 | 结论 |")
    print("|------|------|------|------|")
    for r in rows:
        print(f"| {r['指标']} | {r['阈值']} | {r['实测']} | {r['结论']} |")

    out = Path(os.environ.get("PERF_OUT_DIR") or (ROOT / "docs" / "验收证据" / "20260718_54p8"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "perf_check.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
