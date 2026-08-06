# -*- coding: utf-8 -*-
"""3.7.18 管理端 UX：顶栏上次更新 + 密码列掩码守卫 + 设置页布局契约。

驱动 shipped 纯函数（tsx）与 Vue/CSS 源码契约；禁止仅硬编码期望值绕过实现。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
ADMIN = FE / "admin"
LAST_TS = ADMIN / "utils" / "lastUpdateLabel.ts"
PW_TS = ADMIN / "utils" / "acctPassword.ts"
LAYOUT = ADMIN / "layout" / "AdminLayout.vue"
SETTINGS = ADMIN / "views" / "SettingsView.vue"
SETTINGS_CSS = ADMIN / "views" / "settings-view.css"
ADMIN_CSS = ADMIN / "styles" / "admin.css"
FORM_TS = ADMIN / "composables" / "useSettingsForm.ts"


def _run_tsx_import(module_path: Path, expr_js: str, named: list[str]) -> dict:
    """tsx 加载 shipped 模块，eval 表达式返回 JSON 对象。"""
    url = module_path.resolve().as_uri()
    names = ", ".join(named)
    script = f"""
import {{ {names} }} from '{url}';
const out = ({expr_js});
console.log(JSON.stringify(out));
"""
    env = {**os.environ, "npm_config_yes": "true"}
    candidates = [
        [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsx"), "-e", script],
        ["npx", "--yes", "tsx", "-e", script],
    ]
    last = ""
    for cmd in candidates:
        try:
            r = subprocess.run(
                cmd,
                cwd=str(ROOT / "frontend"),
                capture_output=True,
                text=True,
                timeout=90,
                env=env,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            last = str(e)
            continue
        if r.returncode != 0:
            last = (r.stderr or r.stdout or "")[:600]
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        if not lines:
            last = f"no json in stdout: {r.stdout[:300]}"
            continue
        return json.loads(lines[-1])
    raise AssertionError(f"tsx must run shipped {module_path.name}: {last}")


class TestLastUpdateLabelShipped(unittest.TestCase):
    def test_priority_run_time_over_built_at(self):
        out = _run_tsx_import(
            LAST_TS,
            """(() => {
              const h = {
                run_time: '2026-08-05 12:34:56',
                built_at: '2026-08-01 00:00:00',
                result: '黄',
                run_reasons: ['定时刷新漏跑 2026-08-05：09:30, 12:00'],
              };
              const label = buildLastUpdatePillLabel(h);
              const title = buildLastUpdatePillTitle(h);
              return {
                label,
                title,
                pick: pickLastUpdateRaw(h),
                forbidden: pillHasForbiddenOpsTokens(label),
                titleForbidden: pillHasForbiddenOpsTokens(title),
              };
            })()""",
            [
                "buildLastUpdatePillLabel",
                "buildLastUpdatePillTitle",
                "pickLastUpdateRaw",
                "pillHasForbiddenOpsTokens",
            ],
        )
        self.assertEqual(out["pick"], "2026-08-05 12:34")
        self.assertIn("上次更新 2026-08-05 12:34", out["label"])
        self.assertTrue(out["label"].endswith("▾") or "▾" in out["label"])
        self.assertFalse(out["forbidden"], out["label"])
        self.assertFalse(out["titleForbidden"], out["title"])
        self.assertNotIn("漏跑", out["label"])
        self.assertNotIn("09:30", out["label"])
        self.assertNotIn("定时刷新", out["label"])

    def test_built_at_fallback_and_empty(self):
        only_built = _run_tsx_import(
            LAST_TS,
            "({ label: buildLastUpdatePillLabel({ built_at: '2026-07-01T08:15:00' }), "
            "pick: pickLastUpdateRaw({ built_at: '2026-07-01T08:15:00' }) })",
            ["buildLastUpdatePillLabel", "pickLastUpdateRaw"],
        )
        self.assertRegex(only_built["pick"], r"2026-07-01 0?8:15")
        self.assertIn("上次更新", only_built["label"])
        self.assertNotIn("漏跑", only_built["label"])

        empty = _run_tsx_import(
            LAST_TS,
            "({ label: buildLastUpdatePillLabel({}), empty: LAST_UPDATE_EMPTY })",
            ["buildLastUpdatePillLabel", "LAST_UPDATE_EMPTY"],
        )
        self.assertEqual(empty["empty"], "上次更新 —")
        self.assertIn("上次更新 —", empty["label"])
        self.assertNotIn("漏跑", empty["label"])

    def test_miss_run_reasons_never_in_pill(self):
        out = _run_tsx_import(
            LAST_TS,
            """(() => {
              const h = {
                result: '黄',
                run_time: '2026-08-05 15:00:00',
                run_reasons: ['定时刷新漏跑 2026-08-05：09:30, 12:00', '待补 1 次'],
                warnings: ['某源滞后'],
              };
              const label = buildLastUpdatePillLabel(h);
              return {
                label,
                bad: pillHasForbiddenOpsTokens(label),
                hasMiss: /漏跑|定时刷新|待补|09:30/.test(label),
              };
            })()""",
            ["buildLastUpdatePillLabel", "pillHasForbiddenOpsTokens"],
        )
        self.assertFalse(out["bad"], out["label"])
        self.assertFalse(out["hasMiss"], out["label"])


class TestAcctPasswordMaskShipped(unittest.TestCase):
    def test_fixed_mask_not_submitted(self):
        out = _run_tsx_import(
            PW_TS,
            """(() => {
              const fixed = ACCT_PW_FIXED_MASK;
              return {
                fixed,
                fromFixed: passwordForSave(fixed),
                fromEmpty: passwordForSave(''),
                fromSpaces: passwordForSave('   '),
                fromReal: passwordForSave('secret1'),
              };
            })()""",
            ["ACCT_PW_FIXED_MASK", "passwordForSave"],
        )
        self.assertEqual(out["fixed"], "••••••••")
        self.assertIsNone(out["fromFixed"])
        self.assertIsNone(out["fromEmpty"])
        self.assertIsNone(out["fromSpaces"])
        self.assertEqual(out["fromReal"], "secret1")

    def test_password_set_empty_shows_fixed_readonly(self):
        out = _run_tsx_import(
            PW_TS,
            """(() => {
              const row = { 密码: '', password_set: true, _localNew: false };
              return {
                needs: needsFixedPasswordMask(row),
                display: acctPasswordDisplayValue(row),
                ro: isAcctPasswordReadonly(row),
                reveal: canRevealAcctPassword(row),
                save: passwordForSave(acctPasswordDisplayValue(row)),
              };
            })()""",
            [
                "needsFixedPasswordMask",
                "acctPasswordDisplayValue",
                "isAcctPasswordReadonly",
                "canRevealAcctPassword",
                "passwordForSave",
            ],
        )
        self.assertTrue(out["needs"])
        self.assertEqual(out["display"], "••••••••")
        self.assertTrue(out["ro"])
        self.assertFalse(out["reveal"])
        self.assertIsNone(out["save"])

    def test_real_password_and_local_new(self):
        out = _run_tsx_import(
            PW_TS,
            """(() => {
              const real = { 密码: 'abc123', password_set: true, _localNew: false };
              const neu = { 密码: '', password_set: false, _localNew: true };
              return {
                realDisplay: acctPasswordDisplayValue(real),
                realRo: isAcctPasswordReadonly(real),
                realReveal: canRevealAcctPassword(real),
                newDisplay: acctPasswordDisplayValue(neu),
                newRo: isAcctPasswordReadonly(neu),
                newPh: acctPasswordPlaceholder(neu),
              };
            })()""",
            [
                "acctPasswordDisplayValue",
                "isAcctPasswordReadonly",
                "canRevealAcctPassword",
                "acctPasswordPlaceholder",
            ],
        )
        self.assertEqual(out["realDisplay"], "abc123")
        self.assertFalse(out["realRo"])
        self.assertTrue(out["realReveal"])
        self.assertEqual(out["newDisplay"], "")
        self.assertFalse(out["newRo"])
        self.assertIn("新账号", out["newPh"])


class TestAdminUxSourceContract(unittest.TestCase):
    def test_layout_uses_last_update_helper_no_miss_run_in_pill_path(self):
        src = LAYOUT.read_text(encoding="utf-8")
        self.assertIn("buildLastUpdatePillLabel", src)
        self.assertIn("上次更新", src)
        self.assertIn("healthRunReasons", src)  # 浮层仍绑 run_reasons
        # pill title 不得再拼 run_reasons[0]
        self.assertNotIn("healthRunReasons[0] || healthWarnings[0]", src)
        # 源码无硬编码 miss-run 文案（浮层动态绑 run_reasons 即可）
        self.assertNotIn("漏跑", src)
        self.assertNotIn("定时刷新", src)
        # pill 绑定 helper，不再拼 shortReason / run_reasons[0]
        self.assertNotIn("shortReason", src)
        self.assertIn("healthLabel", src)

    def test_settings_layout_max_width_and_three_ops(self):
        css = SETTINGS_CSS.read_text(encoding="utf-8")
        admin_css = ADMIN_CSS.read_text(encoding="utf-8")
        vue = SETTINGS.read_text(encoding="utf-8")
        # effective max-width 1280–1400
        self.assertRegex(css, r"max-width:\s*1[23]\d{2}px")
        self.assertRegex(admin_css, r"\.admin-root \.settings\s*\{[^}]*max-width:\s*1[23]\d{2}px")
        self.assertIn("scard--ops", vue)
        self.assertIn("自动更新", vue)
        self.assertIn("备份清理", vue)
        self.assertIn("运行日志", vue)
        self.assertIn("智云账号", vue)
        self.assertIn("form-grid-2", vue)
        self.assertIn("acct-pw-row", vue)
        self.assertIn("设新密码", vue)
        self.assertIn("acctPasswordDisplayValue", vue)
        # 禁止旧 placeholder「留空不改」在账号密码列
        acct_block = vue.split('label="密码"')[1].split("el-table-column")[0]
        self.assertNotIn("留空不改", acct_block)

    def test_save_uses_passwordForSave(self):
        form = FORM_TS.read_text(encoding="utf-8")
        self.assertIn("passwordForSave", form)
        self.assertIn("ACCT_PW_FIXED_MASK", form)
        self.assertIn("_localNew", form)
        self.assertIn("toggleAcctPwShow", form)


if __name__ == "__main__":
    unittest.main()
