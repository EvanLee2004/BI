#!/usr/bin/env bash
# 2.3.1 本地看端冒烟（CI 未装 Playwright 时的诚实降级）
# 用法：在程序根目录
#   KANBAN_OFFLINE=1 sh scripts/smoke_cockpit_local.sh
# 需：已 npm run build；tests/fixtures/ci_data 可播种；本机可起 run.py --serve
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export KANBAN_OFFLINE="${KANBAN_OFFLINE:-1}"
PORT="${SMOKE_PORT:-8028}"

if [ ! -d tests/fixtures/ci_data ]; then
  echo "FAIL: missing tests/fixtures/ci_data"
  exit 1
fi

# 结构守卫（不启浏览器也能跑）
python - <<'PY'
from pathlib import Path
root = Path('.')
assert (root / 'frontend/src/utils/countUp.ts').read_text().count('prefersReducedMotion') >= 1
assert 'MIN_SHOW_MS' in (root / 'frontend/src/components/IntroSplash.vue').read_text()
assert 'data-theme="neon"' in (root / 'static/css/theme.css').read_text() or "[data-theme=\"neon\"]" in (root / 'static/css/theme.css').read_text()
assert 'clip-path' in (root / 'frontend/src/vendor/scifi-kit/scifi-bridge.css').read_text()
assert 'transitionToBu' in (root / 'frontend/src/stores/cockpit.ts').read_text()
print('structure smoke OK')
PY

# 可选：若 curl 到本机已有服务则探活
if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/login" 2>/dev/null; then
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/login")
  echo "login HTTP $code"
  [ "$code" = "200" ] || exit 1
  echo "live login OK on :$PORT"
else
  echo "NOTE: no server on :$PORT — structure checks only (start with: python run.py --serve)"
fi
echo "smoke_cockpit_local EXIT:0"
exit 0
