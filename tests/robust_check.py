#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次级鲁棒检查（54.8 · 不进 run_verify）。

用法（服务已起）：
  KANBAN_BASE=http://127.0.0.1:8018 .venv/bin/python tests/robust_check.py

检查：
  - 深链 F5：管理端 orderdept 刷新仍可达
  - 坏输入：手填页数字框填文字后页面不崩（无 pageerror）
  - 双击：刷新按钮连点两次不抛 pageerror

输出表；硬失败 exit 1。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")


def load_accounts():
    for p in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")).get("accounts") or []
    return []


def pick_admin():
    for a in load_accounts():
        if a.get("权限") == "管理员" and a.get("密码"):
            return str(a["账号"]), str(a["密码"])
    return "lushasha", "kanban2026"


def fill_admin(page, acc, pw):
    page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(300)
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
    page.locator("button:has-text('进入'), button:has-text('登录'), .el-button--primary").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("SKIP: playwright 不可用:", e)
        return 2

    rows = []
    hard_fail = False
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: page_errors.append(str(e)[:200]))

        acc, pw = pick_admin()
        fill_admin(page, acc, pw)

        # 深链 + F5
        page.goto(f"{BASE}/admin/review/orderdept", wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector(".toolbar, .el-table", timeout=15000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(".toolbar, .el-table", timeout=15000)
            ok = True
            note = "orderdept 深链+F5 后表格/工具条仍在"
        except Exception as e:
            ok = False
            note = str(e)[:120]
            hard_fail = True
        rows.append({"指标": "深链F5 orderdept", "阈值": "不白屏", "实测": note, "结论": "达标" if ok else "失败"})

        # 坏输入：人工填写（点 .el-input__inner，避开 el-select 的不可 fill 框）
        page.goto(f"{BASE}/admin/edit/manual", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(600)
        n_before = len(page_errors)
        try:
            filled = False
            candidates = page.locator("input.el-input__inner:not([type=password]):not([type=hidden])")
            for i in range(min(candidates.count(), 12)):
                el = candidates.nth(i)
                try:
                    if not el.is_visible() or not el.is_enabled():
                        continue
                    el.click(timeout=3000)
                    el.fill("<script>alert(1)</script>", timeout=5000)
                    page.wait_for_timeout(200)
                    el.fill("not-a-number", timeout=5000)
                    page.wait_for_timeout(300)
                    filled = True
                    break
                except Exception:
                    continue
            if not filled:
                # 无可用手填框：仍以「页面未崩」为通过（环境无字段不算硬失败）
                note = "无可用 el-input__inner，仅确认无 pageerror"
            else:
                note = f"已填脏串 pageerror 增量={len(page_errors) - n_before}"
            ok = len(page_errors) == n_before
            if not ok:
                note = f"pageerror 增量={len(page_errors) - n_before}"
        except Exception as e:
            ok = False
            note = str(e)[:100]
            hard_fail = True
        if not ok:
            hard_fail = True
        rows.append({"指标": "坏输入不崩", "阈值": "无 pageerror", "实测": note, "结论": "达标" if ok else "失败"})

        # 双击刷新
        page.goto(f"{BASE}/admin/review/orderdept", wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        n_before = len(page_errors)
        btn = page.locator("button:has-text('刷新')")
        if btn.count():
            btn.first.dblclick()
            page.wait_for_timeout(500)
        ok = len(page_errors) == n_before
        rows.append(
            {
                "指标": "双击刷新",
                "阈值": "无 pageerror",
                "实测": f"pageerror 增量={len(page_errors)-n_before}",
                "结论": "达标" if ok else "失败",
            }
        )
        if not ok:
            hard_fail = True

        browser.close()

    print("| 指标 | 阈值 | 实测 | 结论 |")
    print("|------|------|------|------|")
    for r in rows:
        print(f"| {r['指标']} | {r['阈值']} | {r['实测']} | {r['结论']} |")
    if page_errors:
        print("page_errors sample:", page_errors[:3])

    out = ROOT / "docs" / "验收证据" / "20260718_54p8"
    out.mkdir(parents=True, exist_ok=True)
    (out / "robust_check.json").write_text(
        json.dumps({"rows": rows, "page_errors": page_errors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
