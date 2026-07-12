@echo off
chcp 65001 >nul
rem 看门狗启动：常驻运行经营罗盘服务，支持管理端「一键更新」后自动重启。
rem 机制：管理端一键更新拉取新代码后，服务进程以退出码 42 退出；本脚本据此用新代码自动重启。
rem       非 42 退出=异常，连续多次(达 5 次)则停下报警，避免坏版本无限重启。
rem 用法：开机自启就把「本脚本」的快捷方式放进 shell:startup（替代 启动看板服务.bat）。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=%~dp0.venv\Scripts\python.exe") else (set "PY=python")
set /a FAILS=0

:loop
echo.
echo [看门狗] 启动服务 %DATE% %TIME%
"%PY%" run.py --serve
set "CODE=%ERRORLEVEL%"

if "%CODE%"=="42" (
  echo [看门狗] 收到「更新后重启」信号(42)，用新代码重启...
  set /a FAILS=0
  timeout /t 2 /nobreak >nul
  goto loop
)

rem 非 42：异常退出（崩溃 / 手动停）。累计异常次数，过多则停下报警。
set /a FAILS+=1
echo [看门狗] 服务退出码=%CODE%（第 %FAILS% 次异常退出）
if %FAILS% GEQ 5 (
  echo.
  echo [看门狗] 连续异常退出过多，停止自动重启。
  echo         可能新版本有问题——请人工检查日志；需回滚上一个版本可跑：
  echo         git -C "%~dp0." reset --hard HEAD~1
  pause
  goto :eof
)
timeout /t 3 /nobreak >nul
goto loop
