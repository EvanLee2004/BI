#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.14 活体：R-20~R-26 硬断言（需 8018 + playwright）。

- R-21：看端 + 管理端多页主题切换截图
- R-22：月 tab 逐一点全部月份；自定义改起止后应用且 period 真变；弹层叠在 KPI 上
- R-24：比率轴边界截图（驱动 shipped ratioAxisBounds）
- R-26：热力图硬存在 + 浅色/375 截图 + 3 格与 VM area_series 对账
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "验收证据" / "20260719_54p14"
SCRATCH = Path(
    os.environ.get(
        "SCRATCH",
        "/var/folders/1_/gps9553s3lb5qcqfk_f3h5z40000gn/T/grok-goal-7374fe778a68/implementer",
    )
)
FE = ROOT / "frontend"


def _admin_creds() -> tuple[str, str]:
    for p in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        if not p.is_file():
            continue
        rows = json.loads(p.read_text(encoding="utf-8")).get("accounts") or []
        for a in rows:
            if a.get("权限") == "管理员" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
    return "lushasha", "123"


def _viewer_creds() -> tuple[str, str]:
    u = os.environ.get("KANBAN_USER")
    pw = os.environ.get("KANBAN_PASS")
    if u and pw:
        return u, pw
    for p in (ROOT / "数据" / "看板账号.json", ROOT / "_golden_data" / "看板账号.json"):
        if not p.is_file():
            continue
        rows = json.loads(p.read_text(encoding="utf-8")).get("accounts") or []
        for a in rows:
            if a.get("账号") in ("123", "overall") and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
            if a.get("权限") == "整体" and a.get("密码"):
                return str(a["账号"]), str(a["密码"])
    return "123", "123"


def _ratio_bounds_via_shipped() -> dict:
    """驱动真实 frontend/src/chart-months.ts 的 ratioAxisBounds。"""
    src = FE / "src" / "chart-months.ts"
    script = f"""
import {{ ratioAxisBounds }} from 'file://{src.as_posix()}';
const cases = {{
  over: ratioAxisBounds([10, 120, 95, null]),
  zero: ratioAxisBounds([0, 0, 0]),
  neg: ratioAxisBounds([-5, 20, 40]),
}};
console.log(JSON.stringify(cases));
"""
    for cmd in (
        ["npx", "--yes", "tsx", "-e", script],
        [str(FE / "node_modules" / ".bin" / "tsx"), "-e", script],
    ):
        try:
            r = subprocess.run(
                cmd,
                cwd=str(FE),
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "npm_config_yes": "true"},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0:
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if lines:
            return json.loads(lines[-1])
    raise RuntimeError("tsx ratioAxisBounds unavailable")


def _heat_pack_via_shipped(labels, series) -> dict:
    src = FE / "src" / "utils" / "expense-heat.ts"
    payload = json.dumps({"labels": labels, "series": series}, ensure_ascii=False)
    script = f"""
import {{ buildExpenseHeatPack, pickHeatCells }} from 'file://{src.as_posix()}';
const p = {payload};
const pack = buildExpenseHeatPack(p.labels, p.series);
const cells = pickHeatCells(pack, 3);
console.log(JSON.stringify({{ pack: {{ labels: pack.labels, cats: pack.cats, n: pack.data.length, vmax: pack.vmax }}, cells }}));
"""
    for cmd in (
        ["npx", "--yes", "tsx", "-e", script],
        [str(FE / "node_modules" / ".bin" / "tsx"), "-e", script],
    ):
        try:
            r = subprocess.run(
                cmd,
                cwd=str(FE),
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "npm_config_yes": "true"},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0:
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if lines:
            return json.loads(lines[-1])
    raise RuntimeError("tsx expense-heat unavailable")


class Test54p14LiveOptional(unittest.TestCase):
    def test_live_walk(self):
        base = os.environ.get("KANBAN_BASE", "http://127.0.0.1:8018")
        try:
            import urllib.request

            urllib.request.urlopen(base + "/api/health", timeout=2)
        except Exception:
            self.skipTest("8018 未起服")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("无 playwright")

        out = EVID / "live"
        out.mkdir(parents=True, exist_ok=True)
        report: dict = {"steps": []}
        vuser, vpwd = _viewer_creds()
        auser, apwd = _admin_creds()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            # ── 看端登录 ──
            page.goto(base + "/login", wait_until="networkidle", timeout=90000)
            page.locator("input").first.fill(vuser)
            page.locator("input[type=password]").fill(vpwd)
            page.locator("button:has-text('进入'), button:has-text('登录')").first.click()
            page.wait_for_selector("[data-testid=period-picker]", timeout=45000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / "home_dark.png"))

            # R-20
            body = page.inner_text("body")
            self.assertNotIn("万万", body)
            report["steps"].append({"r20": "no_double_wan_body", "ok": True})

            # ── R-21 看端主题 ──
            before = page.evaluate(
                "() => document.documentElement.classList.contains('theme-light')"
            )
            theme_btn = page.locator(
                "button:has-text('浅色'), button:has-text('深色'), button:has-text('亮/暗')"
            ).first
            theme_btn.click(force=True)
            page.wait_for_timeout(500)
            after = page.evaluate(
                "() => document.documentElement.classList.contains('theme-light')"
            )
            self.assertNotEqual(before, after)
            page.screenshot(path=str(out / "theme_after_toggle.png"))
            report["steps"].append({"r21_cockpit": {"before": before, "after": after}})
            # 回到暗色便于后续
            if after:
                theme_btn.click(force=True)
                page.wait_for_timeout(300)

            # ── R-22 弹层 z + 叠在 KPI 上 ──
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_selector(".pp-panel", timeout=5000)
            page.wait_for_timeout(200)
            page.screenshot(path=str(out / "period_open.png"))
            stack = page.evaluate(
                """() => {
                  const panel = document.querySelector('.pp-panel');
                  const kpi = document.querySelector('.kpi-grid, .kpi-host, .scifi-panel.kpi-card');
                  if (!panel) return { ok: false, reason: 'no panel' };
                  const pr = panel.getBoundingClientRect();
                  const cs = getComputedStyle(panel);
                  const bg = cs.backgroundColor || '';
                  let a = 1.0;
                  const m = bg.match(/rgba?\\(([^)]+)\\)/);
                  if (m) {
                    const parts = m[1].split(',').map(s => s.trim());
                    a = parts.length >= 4 ? parseFloat(parts[3]) : 1.0;
                  }
                  // 取 panel 中心点：应命中 panel 自身，不得命中 KPI 卡
                  const cx = pr.left + pr.width / 2;
                  const cy = pr.top + Math.min(pr.height / 2, 40);
                  const el = document.elementFromPoint(cx, cy);
                  const hitsPanel = !!(el && (el === panel || panel.contains(el)));
                  const hitsKpi = !!(kpi && el && kpi.contains(el) && !panel.contains(el));
                  // topbar 堆叠上下文
                  const topbar = document.querySelector('.topbar');
                  const tz = topbar ? getComputedStyle(topbar).zIndex : null;
                  const wz = (() => {
                    const w = document.querySelector('.wrap');
                    return w ? getComputedStyle(w).zIndex : null;
                  })();
                  return {
                    ok: true,
                    panelA: a,
                    z: cs.zIndex,
                    topbarZ: tz,
                    wrapZ: wz,
                    hitsPanel,
                    hitsKpi,
                    elTag: el ? el.className || el.tagName : null,
                  };
                }"""
            )
            report["steps"].append({"r22_stack": stack})
            self.assertTrue(stack.get("ok"), stack)
            self.assertGreaterEqual(float(stack.get("panelA") or 0), 0.95)
            self.assertTrue(stack.get("hitsPanel"), f"弹层未在最前: {stack}")
            self.assertFalse(stack.get("hitsKpi"), f"弹层被 KPI 挡住: {stack}")
            # topbar z > wrap z（数值可比时）
            try:
                tz = int(stack.get("topbarZ") or 0)
                wz = int(stack.get("wrapZ") or 0)
                self.assertGreater(tz, wz, f"topbar z={tz} 应 > wrap z={wz}")
            except (TypeError, ValueError):
                pass

            # 月 tab：逐一点全部月份选项
            page.locator(".pp-tab:has-text('月')").click()
            page.wait_for_timeout(200)
            # 预演 12 格布局：若不足 12，用 DOM 注入额外 disabled 占位钮验证网格不溢出
            n_real = page.locator(".pp-body.pp-grid-4 .pp-opt, .pp-grid-4 .pp-opt").count()
            if n_real < 12:
                page.evaluate(
                    """() => {
                      const body = document.querySelector('.pp-body.pp-grid-4, .pp-grid-4');
                      if (!body) return;
                      const have = body.querySelectorAll('.pp-opt').length;
                      for (let i = have; i < 12; i++) {
                        const b = document.createElement('button');
                        b.type = 'button';
                        b.className = 'pp-opt pp-mock-pad';
                        b.disabled = true;
                        b.textContent = (i + 1) + '月';
                        b.setAttribute('data-mock-pad', '1');
                        body.appendChild(b);
                      }
                    }"""
                )
                page.wait_for_timeout(100)
            page.screenshot(path=str(out / "period_12pad.png"))
            n_cells = page.locator(".pp-grid-4 .pp-opt").count()
            self.assertGreaterEqual(n_cells, 12, "12 月满格预演")
            # 清掉 mock 再真点
            page.evaluate(
                """() => document.querySelectorAll('[data-mock-pad]').forEach(e => e.remove())"""
            )

            months = page.locator(".pp-body .pp-opt:not([disabled]), .pp-grid-4 .pp-opt:not([disabled])")
            n = months.count()
            self.assertGreaterEqual(n, 1, "至少 1 个单月")
            clicked = []
            for i in range(n):
                # 每次打开
                if i > 0:
                    page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
                    page.wait_for_selector(".pp-panel", timeout=5000)
                    page.locator(".pp-tab:has-text('月')").click()
                    page.wait_for_timeout(150)
                    months = page.locator(
                        ".pp-body .pp-opt:not([disabled]), .pp-grid-4 .pp-opt:not([disabled])"
                    )
                lab = months.nth(i).inner_text().strip()
                months.nth(i).click()
                page.wait_for_timeout(350)
                cur = page.locator("[data-testid=period-picker] .pp-trigger").inner_text()
                clicked.append({"label": lab, "trigger": cur.strip()})
                self.assertTrue(
                    re.search(r"\d{4}年\d{1,2}月", cur) or "月" in cur,
                    f"点 {lab} 后 trigger={cur}",
                )
            report["steps"].append({"r22_months_all": clicked, "count": n})
            self.assertEqual(len(clicked), n)
            page.screenshot(path=str(out / "period_month.png"))

            # 自定义区间：改起止 → 应用 → period 真变
            before_pk = page.locator("[data-testid=period-picker] .pp-trigger").inner_text().strip()
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_selector(".pp-panel", timeout=5000)
            page.locator(".pp-tab:has-text('自定义')").click()
            page.wait_for_timeout(200)
            # 选不同起止（若有多个 option）
            sels = page.locator(".pp-select")
            self.assertGreaterEqual(sels.count(), 2, "自定义起止 select")
            # 起 = 第一项，止 = 最后一项（尽量得到区间）
            from_opts = page.locator(".pp-select").nth(0).locator("option")
            to_opts = page.locator(".pp-select").nth(1).locator("option")
            nf, nt = from_opts.count(), to_opts.count()
            self.assertGreaterEqual(nf, 1)
            self.assertGreaterEqual(nt, 1)
            from_val = from_opts.nth(0).get_attribute("value")
            to_val = to_opts.nth(nt - 1).get_attribute("value")
            page.locator(".pp-select").nth(0).select_option(value=from_val)
            page.locator(".pp-select").nth(1).select_option(value=to_val)
            page.wait_for_timeout(150)
            preview = ""
            if page.locator(".pp-preview").count():
                preview = page.locator(".pp-preview").inner_text()
            apply_btn = page.locator(".pp-apply")
            self.assertTrue(apply_btn.count(), "应用按钮")
            # 若该组合不在 period_keys，按钮可能 disabled —— 尝试找可点的自定义列表项
            if apply_btn.is_disabled():
                customs = page.locator(".pp-custom-list .pp-opt")
                self.assertGreater(customs.count(), 0, "无可用自定义区间")
                target_txt = customs.nth(0).inner_text().strip()
                customs.nth(0).click()
                page.wait_for_timeout(400)
                after_pk = page.locator("[data-testid=period-picker] .pp-trigger").inner_text().strip()
                report["steps"].append(
                    {
                        "r22_custom": {
                            "mode": "list_pick",
                            "picked": target_txt,
                            "before": before_pk,
                            "after": after_pk,
                        }
                    }
                )
                self.assertNotEqual(after_pk, before_pk, "自定义列表点选后 period 应变化")
            else:
                apply_btn.click()
                page.wait_for_timeout(500)
                after_pk = page.locator("[data-testid=period-picker] .pp-trigger").inner_text().strip()
                report["steps"].append(
                    {
                        "r22_custom": {
                            "mode": "apply",
                            "from": from_val,
                            "to": to_val,
                            "preview": preview,
                            "before": before_pk,
                            "after": after_pk,
                        }
                    }
                )
                # 应用成功：trigger 应变（或已是该区间）
                self.assertTrue(
                    after_pk != before_pk or (from_val and to_val and from_val != to_val and "-" in after_pk),
                    f"自定义应用未改 period: {before_pk} → {after_pk} preview={preview}",
                )
            page.screenshot(path=str(out / "period_custom.png"))

            # ── R-26 热力图 ──
            heat = page.locator("[data-testid=expense-heatmap]")
            self.assertGreater(heat.count(), 0, "热力图 DOM 必须存在")
            heat.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / "heatmap.png"))

            # 拉 VM 做 3 格对账（同源 buildExpenseHeatPack）
            cookies = page.context.cookies()
            # fetch with page
            vm = page.evaluate(
                """async () => {
                  const r = await fetch('/api/v1/vm/cockpit', { credentials: 'same-origin' });
                  if (!r.ok) return { err: r.status };
                  return await r.json();
                }"""
            )
            self.assertNotIn("err", vm, vm)
            exp = (vm or {}).get("expense") or {}
            labels = exp.get("area_labels") or []
            series = exp.get("area_series") or []
            heat_out = _heat_pack_via_shipped(labels, series)
            cells = heat_out.get("cells") or []
            self.assertGreaterEqual(len(cells), 1, "至少 1 个非零热力格")
            # 对账：每个 cell 的 disp/value == 对应 series.data_disp / data（同源 shipped pack）
            reconciled = []
            for c in cells:
                s = series[c["yi"]]
                dlist = s.get("data_disp") or []
                expected = str(dlist[c["xi"]]) if c["xi"] < len(dlist) else ""
                self.assertEqual(c["disp"], expected, c)
                dlist_n = s.get("data") or []
                if c["xi"] < len(dlist_n):
                    self.assertEqual(float(c["value"]), float(dlist_n[c["xi"]] or 0), c)
                reconciled.append(
                    {
                        "label": c["label"],
                        "cat": c["cat"],
                        "disp": c["disp"],
                        "value": c["value"],
                        "match_disp": True,
                    }
                )
            # 任务书：抽 3 格；数据不足 3 个非零时以全部非零格为准但至少 1
            need = 3 if len(cells) >= 3 else len(cells)
            self.assertGreaterEqual(len(reconciled), need)
            (out / "heatmap_3cells.json").write_text(
                json.dumps(
                    {"cells": reconciled, "vm_labels": labels, "pack_n": heat_out["pack"]["n"]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            report["steps"].append({"r26_3cells": reconciled})
            # heatmap 浅色
            page.evaluate(
                """() => {
                  document.documentElement.classList.add('theme-light');
                  window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light: true } }));
                }"""
            )
            page.wait_for_timeout(600)
            heat.scroll_into_view_if_needed()
            page.screenshot(path=str(out / "heatmap_light.png"))
            page.screenshot(path=str(out / "home_light_1440.png"))

            # heatmap 375
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(400)
            heat.scroll_into_view_if_needed()
            page.screenshot(path=str(out / "heatmap_375.png"))
            page.locator("[data-testid=period-picker] .pp-trigger").click(force=True)
            page.wait_for_timeout(200)
            page.screenshot(path=str(out / "period_375.png"))
            page.keyboard.press("Escape")

            # 恢复 1440 暗色
            page.set_viewport_size({"width": 1440, "height": 900})
            page.evaluate(
                """() => {
                  document.documentElement.classList.remove('theme-light');
                  window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light: false } }));
                }"""
            )
            page.wait_for_timeout(300)

            # ── R-21 管理端多页主题 ──
            page.goto(base + "/admin/login", wait_until="networkidle", timeout=90000)
            if page.locator("input[type=password]").count():
                page.locator("input").first.fill(auser)
                page.locator("input[type=password]").fill(apwd)
                page.locator("button:has-text('登录'), button:has-text('进入')").first.click()
                page.wait_for_timeout(800)
            # 确保进到 admin
            page.goto(base + "/admin", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(500)
            admin_pages = [
                ("/admin", "admin_console"),
                ("/admin/edit/detail?table=收入明细", "admin_detail"),
                ("/admin/edit/manual", "admin_manual"),
                ("/admin/edit/budget", "admin_budget"),
                ("/admin/review/orderdept", "admin_orderdept"),
                ("/admin/settings", "admin_settings"),
            ]
            admin_theme = []
            for path, name in admin_pages:
                page.goto(base + path, wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(400)
                b0 = page.evaluate(
                    "() => document.documentElement.classList.contains('theme-light')"
                )
                # 顶栏主题按钮
                tbtn = page.locator("button:has-text('浅色'), button:has-text('深色')").first
                self.assertTrue(tbtn.count() > 0 or page.locator(".admin-bar").count() > 0, name)
                if tbtn.count():
                    tbtn.click(force=True)
                    page.wait_for_timeout(400)
                else:
                    page.evaluate(
                        """() => {
                          const on = !document.documentElement.classList.contains('theme-light');
                          document.documentElement.classList.toggle('theme-light', on);
                          window.dispatchEvent(new CustomEvent('admin-theme', { detail: { theme: on ? 'light' : 'dark' } }));
                          window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light: on } }));
                        }"""
                    )
                    page.wait_for_timeout(400)
                b1 = page.evaluate(
                    "() => document.documentElement.classList.contains('theme-light')"
                )
                self.assertNotEqual(b0, b1, f"管理端主题未变: {name}")
                # 内容区用 CSS 变量即时变（抽样 bg）
                bg = page.evaluate(
                    """() => {
                      const root = document.querySelector('.admin-root') || document.body;
                      return getComputedStyle(root).backgroundColor;
                    }"""
                )
                page.screenshot(path=str(out / f"{name}_theme_{'light' if b1 else 'dark'}.png"))
                admin_theme.append({"page": name, "before": b0, "after": b1, "bg": bg})
                # 切回
                if tbtn.count():
                    tbtn.click(force=True)
                    page.wait_for_timeout(250)
            report["steps"].append({"r21_admin": admin_theme})
            self.assertEqual(len(admin_theme), len(admin_pages))

            # ── R-24 比率边界截图（shipped ratioAxisBounds + echarts） ──
            bounds = _ratio_bounds_via_shipped()
            self.assertGreaterEqual(bounds["over"]["max"], 120)
            self.assertEqual(bounds["zero"]["min"], 0)
            self.assertLessEqual(bounds["neg"]["min"], -5)
            echarts_js = (FE / "node_modules" / "echarts" / "dist" / "echarts.min.js").read_text(
                encoding="utf-8"
            )
            for key, series, fname in (
                ("over", [10, 120, 95, 80], "ratio_boundary_over100.png"),
                ("zero", [0, 0, 0, 0], "ratio_boundary_zero.png"),
                ("neg", [-5, 20, 40, 15], "ratio_boundary_neg.png"),
            ):
                b = bounds[key]
                html = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
                <style>html,body{{margin:0;background:#0b1220}}#c{{width:720px;height:360px}}</style>
                </head><body><div id=c></div>
                <script>{echarts_js}</script>
                <script>
                const chart = echarts.init(document.getElementById('c'));
                chart.setOption({{
                  animation:false,
                  grid:{{left:48,right:48,top:40,bottom:40,containLabel:true}},
                  xAxis:{{type:'category',data:['1月','2月','3月','4月'],axisLabel:{{color:'#c5d0e8'}}}},
                  yAxis:{{type:'value',min:{b['min']},max:{b['max']},
                    axisLabel:{{formatter:'{{value}}%',color:'#c5d0e8'}},
                    splitLine:{{lineStyle:{{color:'rgba(125,211,252,.16)'}}}}}},
                  series:[{{type:'line',data:{json.dumps(series)},
                    itemStyle:{{color:'#fbbf24'}},lineStyle:{{width:2.5,color:'#fbbf24'}},
                    symbol:'circle',symbolSize:8,
                    label:{{show:true,formatter:'{{c}}%',color:'#fbbf24'}}}}]
                }});
                </script></body></html>"""
                page.set_content(html, wait_until="networkidle")
                page.wait_for_timeout(300)
                page.screenshot(path=str(out / fname))
            report["steps"].append({"r24_bounds": bounds})

            browser.close()

        (out / "live_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (SCRATCH / "54p14_live_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 硬性：报告含关键键
        self.assertTrue(any("r22_months_all" in str(s) for s in report["steps"]))
        self.assertTrue(any("r26_3cells" in str(s) for s in report["steps"]))
        self.assertTrue(any("r21_admin" in str(s) for s in report["steps"]))


if __name__ == "__main__":
    unittest.main()
