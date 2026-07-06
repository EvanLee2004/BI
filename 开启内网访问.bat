@echo off
rem 经营驾驶舱：在本机 8018 端口开内网访问（只共享 output\ 目录，源数据绝不暴露）
rem 开着这个窗口期间，同事用浏览器访问  http://本机IP:8018/经营驾驶舱.html
rem ⚠ 注意：http.server 没有账号密码，开端口前先确认访问控制方案已经陆经理同意。
chcp 65001 >nul
cd /d "%~dp0output"
echo 本机 IP 地址（发给需要看的人，选“IPv4 地址”那一行）：
ipconfig | findstr /i "IPv4"
echo.
echo 访问地址： http://上面的IP:8018/经营驾驶舱.html
echo 关闭本窗口 = 停止访问。
python -m http.server 8018
