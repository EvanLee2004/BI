@echo off
chcp 65001 >nul
rem 注册 Windows 计划任务：每天定时跑 run.py --scheduled（更新库+出页面）。
rem 时间取 config.json 的 schedule_time（缺省 09:30）；改时间后重跑本脚本即可覆盖注册。
rem 需管理员权限运行（右键"以管理员身份运行"）。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=%~dp0.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

rem 读 config 里的 schedule_time
set "RUNTIME=09:30"
for /f "delims=" %%t in ('"%PY%" -c "import json;print(json.load(open('config.json')).get('schedule_time') or '09:30')"') do set "RUNTIME=%%t"

set "TN=经营驾驶舱每日更新"
echo 将注册计划任务：%TN%  每天 %RUNTIME% 运行 run.py --scheduled
schtasks /Create /TN "%TN%" /SC DAILY /ST %RUNTIME% /F ^
  /TR "\"%PY%\" \"%~dp0run.py\" --scheduled"

if %ERRORLEVEL%==0 (
  echo.
  echo [OK] 已注册。可用 schtasks /Query /TN "%TN%" 查看，或在"任务计划程序"里查。
) else (
  echo.
  echo [失败] 注册未成功——请确认以"管理员身份"运行本脚本。
)
pause
