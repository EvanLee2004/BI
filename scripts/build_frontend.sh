#!/bin/sh
# 构建 Vue 前端 → frontend/dist（进 git；CI 重建后 diff）
set -e
cd "$(dirname "$0")/../frontend"
if [ ! -d node_modules ]; then
  npm ci 2>/dev/null || npm install
fi
npm run build
echo "✓ frontend/dist 已构建"
ls -la dist | head
