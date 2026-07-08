@echo off
chcp 65001 >nul
rem 启动经营驾驶舱内网服务：用户端 http://本机IP:8018/  管理员端 /admin
rem 优先用项目 venv 的 python（含 fastapi/uvicorn/openpyxl）；没有则用系统 python。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo 正在启动看板服务（Ctrl+C 停止）...
"%PY%" run.py --serve
echo.
echo 服务已退出。
pause
