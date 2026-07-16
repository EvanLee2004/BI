@echo off
chcp 65001 >nul
rem 经营罗盘：放行本机 TCP 8018 入站（内网同事/手机访问 http://本机IP:8018/）
rem ⚠ 需「以管理员身份运行」。服务本身请用 看门狗启动.bat（本脚本只开防火墙，不启服务）。
rem 历史：旧版曾用 python -m http.server 共享 output\，已废弃（无鉴权、非双端服务）。
cd /d "%~dp0"
echo 正在添加 Windows 防火墙入站规则：甲骨易经营罗盘-8018 ...
netsh advfirewall firewall delete rule name="甲骨易经营罗盘-8018" >nul 2>&1
netsh advfirewall firewall add rule name="甲骨易经营罗盘-8018" dir=in action=allow protocol=TCP localport=8018 profile=private,domain
if errorlevel 1 (
  echo [失败] 请右键本脚本 →「以管理员身份运行」，再试一次。
  pause
  exit /b 1
)
echo [完成] 已放行 TCP 8018（专用/域网络配置文件）。
echo 请确认 看门狗启动.bat 已在跑；同事访问：http://本机IP:8018/
echo 本机 IPv4：
ipconfig | findstr /i "IPv4"
pause
