# 第 11 关 · 上线扫尾

## 控制台
- 见 `../05_生产就绪/console_capture.json`：`page_errors=0`，`console_js_clean=true`  
- 网络 401/404 console 噪声已归因

## 版本一致
```
VERSION=2.0.0-beta
frontend/package.json version=2.0.0-beta
```

## 依赖扫
- `cd frontend && npm audit --omit=dev`（2026-07-18）：
  - **echarts &lt;6.1.0** moderate XSS（GHSA-fgmj-fm8m-jvvx）— 看板只渲染后端 `*_disp` 显示串，不把未转义用户 HTML 喂进 ECharts rich text；**不升 major（breaking）**，记知悉
  - **element-plus ≤2.11.0** moderate el-link href — 管理端主路径未依赖任意 href 用户输入 `el-link`；可选后续小版本升级
- pip：核心包 fastapi/uvicorn 在 venv 中（见本机 `pip list`）

## 登录防爆破
- 既有服务端限速/锁定逻辑以 `tests/test_auth.py` 等为准（run_verify 绿）；本轮未改 auth 代码

## 构建
- R-00 修复后已 `npm run build` 并提交 `frontend/dist`
