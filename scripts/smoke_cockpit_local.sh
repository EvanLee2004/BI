#!/usr/bin/env bash
# 2.3.1 本地看端冒烟（CI 未装 Playwright 全链路时的诚实降级）
#
# 覆盖范围（诚实声明）：
#   1) 结构守卫：源码契约（count-up / intro / neon 选择器 / BU 转场）
#   2) 可选活体：若 SMOKE_PORT 已有服务 → curl login +（有 playwright 时）登录→切主题→无 console error
#   不做：CI 内 headless 全页回归（未进 verify.yml，避免装浏览器成本与 flaky）
#
# 用法（程序根目录）：
#   KANBAN_OFFLINE=1 sh scripts/smoke_cockpit_local.sh
# 建议：先用 _golden_data 起服
#   # 临时：数据/本地配置.json 写 {"data_dir":"_golden_data"}
#   KANBAN_PORT=8028 KANBAN_OFFLINE=1 python run.py --serve
# 全量截图：
#   KANBAN_BASE=http://127.0.0.1:8028 .venv/bin/python scripts/capture_2_3_1_visual.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export KANBAN_OFFLINE="${KANBAN_OFFLINE:-1}"
PORT="${SMOKE_PORT:-8028}"
BASE="http://127.0.0.1:${PORT}"

if [ ! -d tests/fixtures/ci_data ]; then
  echo "FAIL: missing tests/fixtures/ci_data"
  exit 1
fi

# ── 1) 结构守卫 ──
python - <<'PY'
from pathlib import Path
root = Path('.')
assert (root / 'frontend/src/utils/countUp.ts').read_text().count('prefersReducedMotion') >= 1
assert 'MIN_SHOW_MS' in (root / 'frontend/src/components/IntroSplash.vue').read_text()
theme = (root / 'static/css/theme.css').read_text()
assert 'data-theme="neon"' in theme or '[data-theme="neon"]' in theme or "data-theme=\"neon\"" in theme or ":root[data-theme=\"neon\"]" in theme
assert 'clip-path' in (root / 'frontend/src/vendor/scifi-kit/scifi-bridge.css').read_text()
assert 'transitionToBu' in (root / 'frontend/src/stores/cockpit.ts').read_text()
print('structure smoke OK')
PY

# ── 2) 可选活体 ──
if curl -sf -o /dev/null "${BASE}/login" 2>/dev/null; then
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/login")
  echo "login HTTP $code"
  [ "$code" = "200" ] || exit 1
  if .venv/bin/python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    KANBAN_BASE="$BASE" .venv/bin/python - <<'PY'
import json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = os.environ["KANBAN_BASE"]
ROOT = Path(".").resolve()
acc, pw = "overall", "8888"
for p in (ROOT / "_golden_data" / "看板账号.json", ROOT / "数据" / "看板账号.json"):
    if p.is_file():
        for a in json.loads(p.read_text(encoding="utf-8")).get("accounts") or []:
            if a.get("账号") in ("overall", "123") and a.get("密码"):
                acc, pw = str(a["账号"]), str(a["密码"])
                break
        break
errs = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    page.locator("input").first.fill(acc)
    page.locator("input[type=password]").fill(pw)
    page.locator("button:has-text('进入'), button:has-text('登录')").first.click()
    page.wait_for_selector("[data-testid=period-picker], .kpi-grid", timeout=45000)
    # 切主题一圈
    btn = page.locator("button:has-text('浅色'), button:has-text('深色'), button:has-text('霓虹')").first
    themes = []
    for _ in range(3):
        btn.click(force=True)
        page.wait_for_timeout(350)
        themes.append(page.evaluate("() => document.documentElement.dataset.theme"))
    # 周期钮可点
    page.locator("[data-testid=period-picker] .pp-trigger, [data-testid=period-picker]").first.click(force=True)
    page.wait_for_timeout(300)
    browser.close()
print("live smoke OK themes=", themes, "console_errors=", len(errs))
if len(errs) > 5:
    print("WARN many console errors", errs[:5])
    sys.exit(1)
PY
    echo "live browser smoke OK on :$PORT"
  else
    echo "NOTE: playwright 不可用 — 仅 curl login 探活（非完整活体）"
  fi
else
  echo "NOTE: no server on :$PORT — structure checks only"
  echo "  start: KANBAN_PORT=$PORT KANBAN_OFFLINE=1 python run.py --serve"
fi
echo "smoke_cockpit_local EXIT:0 (structure + optional live; NOT full CI Playwright job)"
exit 0
