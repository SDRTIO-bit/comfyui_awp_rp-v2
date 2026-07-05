@echo off
REM AWP RP Runtime 独立服务器 - 双击启动
cd /d "%~dp0.."
python scripts/awp_server.py
pause
