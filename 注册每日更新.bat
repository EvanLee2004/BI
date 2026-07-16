@echo off
chcp 65001 >nul
rem 注册 Windows 计划任务：每天在「合并配置」(config.json + 数据/本地配置.json 覆盖层) 的 schedule_times 每个时间点各跑一次 run.py --scheduled。
rem 多个时间点=多个任务：主任务名『经营驾驶舱每日更新』(最早时间点) + _2.._n(其余时间点)。
rem 改/增删时间点后重跑本脚本即可覆盖注册（管理端「设置」保存也会尝试自动同步，失败再跑本脚本）。
rem 需管理员权限运行（右键"以管理员身份运行"）。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=%~dp0.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set "TN=经营驾驶舱每日更新"

rem 先清理旧的编号任务（_2.._6），避免删掉时间点后残留
for %%i in (2 3 4 5 6) do schtasks /Delete /TN "%TN%_%%i" /F >nul 2>&1

rem 读「合并配置」的 schedule_times（空格分隔）；缺失回退旧 schedule_time / 09:30。
rem 必须走 loaders.load_config（config.json + 数据/本地配置.json 覆盖层，铁律19）——管理端保存的时间点只存覆盖层，直接读 config.json 会永远拿到出厂默认。
set "TIMES="
for /f "delims=" %%t in ('"%PY%" -c "import sys;sys.path.insert(0,'src');import loaders;c=loaders.load_config();ts=c.get('schedule_times') or [c.get('schedule_time') or '09:30'];print(' '.join(ts))"') do set "TIMES=%%t"
if "%TIMES%"=="" set "TIMES=09:30"

set /a IDX=0
for %%t in (%TIMES%) do (
  set /a IDX+=1
  call :reg %%t
)
echo.
echo [完成] 已按 %TIMES% 注册计划任务。可用 schtasks /Query ^| findstr "%TN%" 查看，或在"任务计划程序"里查。
pause
goto :eof

:reg
if "%IDX%"=="1" (set "NAME=%TN%") else (set "NAME=%TN%_%IDX%")
echo 注册 %NAME%  每天 %1 运行 run.py --scheduled
rem TR 用 cmd /c + cd /d 固定起始目录（计划任务默认 cwd 常为 System32；程序虽用 __file__ 定位根目录，仍显式 cd 更稳）
schtasks /Create /TN "%NAME%" /SC DAILY /ST %1 /F ^
  /TR "cmd /c \"cd /d \"\"%~dp0\"\" && \"\"%PY%\"\" run.py --scheduled\""
if not %ERRORLEVEL%==0 echo   [失败] %NAME% 注册未成功——请确认以"管理员身份"运行本脚本。
goto :eof
