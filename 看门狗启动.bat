@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem 看门狗启动：常驻运行经营罗盘服务，支持管理端「一键更新」后自动重启 + 坏版本自愈。
rem 机制：
rem   - 管理端一键更新拉取新代码（并自动 pip install 变化的依赖）后，服务进程以退出码 42 退出；本脚本据此用新代码自动重启。
rem   - 若「更新后启动就崩」（存在回滚点标记 .update_rollback）：自动回滚到更新前版本再重启一次（自愈）。
rem   - 其它非 42 异常退出：累计次数，连续达 5 次则停下报警，避免坏版本无限重启。
rem 用法：开机自启就把「本脚本」的快捷方式放进 shell:startup（替代 启动看板服务.bat）。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=%~dp0.venv\Scripts\python.exe") else (set "PY=python")
set /a FAILS=0

:loop
echo.
echo [看门狗] 启动服务 %DATE% %TIME%
"%PY%" run.py --serve
set "CODE=!ERRORLEVEL!"

if "!CODE!"=="42" (
  echo [看门狗] 收到「更新后重启」信号^(42^)，用新代码重启...
  set /a FAILS=0
  timeout /t 2 /nobreak >nul
  goto loop
)

rem 非 42：异常退出（崩溃 / 手动停）。
rem 先看有没有「更新回滚点」标记——有=刚更新完就崩，自动回滚一次到更新前版本再起
rem （只回滚一次：删标记后若再崩就走下面的计数报警，避免来回死循环）。
if exist ".update_rollback" (
  set "PREV="
  set /p PREV=<.update_rollback
  del /q ".update_rollback" >nul 2>&1
  echo [看门狗] 更新后启动异常^(码=!CODE!^)——自动回滚到更新前版本 !PREV! ...
  git -C "%~dp0." reset --hard !PREV!
  if errorlevel 1 (
    echo [看门狗] ^^!回滚失败，请人工检查：git -C "%~dp0." reset --hard !PREV!
    pause
    goto :eof
  )
  set /a FAILS=0
  timeout /t 3 /nobreak >nul
  goto loop
)

rem 无回滚标记：普通异常，累计次数，过多则停下报警。
set /a FAILS+=1
echo [看门狗] 服务退出码=!CODE!（第 !FAILS! 次异常退出）
if !FAILS! GEQ 5 (
  echo.
  echo [看门狗] 连续异常退出过多，停止自动重启。
  echo         可能新版本有问题——请人工检查日志；需回滚上一个版本可跑：
  echo         git -C "%~dp0." reset --hard HEAD~1
  pause
  goto :eof
)
timeout /t 3 /nobreak >nul
goto loop
