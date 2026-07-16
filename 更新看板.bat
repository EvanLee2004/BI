@echo off
chcp 65001 >nul
rem 经营驾驶舱：更新一次报表（读 数据\ 里 6 个源文件 → 生成 output\经营驾驶舱.html）
rem 双击运行，或由任务计划程序每天定时调用。
rem 优先用项目 .venv\Scripts\python.exe（与看门狗/注册脚本一致）。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=%~dp0.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" run.py
if errorlevel 1 (
    echo.
    echo ======================================================
    echo  生成失败：请看上方“数据进门验证”里指出的具体问题，
    echo  修好 数据\ 里对应的源文件后重新双击本脚本。
    echo ======================================================
    pause
    exit /b 1
)
echo.
echo 生成成功：output\经营驾驶舱.html
rem 定时任务静默跑时不想停住的话，把下面这行 pause 删掉即可
pause
