@echo off
chcp 65001 >nul
title 网页侦察器 (web-recon)
cd /d "%~dp0"
set OUT=D:\Documents\网页侦察输出
if not exist "%OUT%" mkdir "%OUT%"

echo ============================================
echo   网页侦察器  -  扫描当前浏览器页面生成地图
echo ============================================
echo.
echo 当前可扫描的页面:
python scan_page.py --list
echo.
set /p M=输入要扫描页面的关键词(直接回车=自动挑电商后台页): 
echo.
if "%M%"=="" (
    python scan_page.py --out "%OUT%"
) else (
    python scan_page.py --match "%M%" --out "%OUT%"
)
echo.
echo 完成! 地图已保存到: %OUT%
explorer "%OUT%"
echo.
pause
