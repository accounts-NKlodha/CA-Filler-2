@echo off
rem Lodha OS on this computer only. Use start_lan.bat to let the office open it.
cd /d "%~dp0"
python -m lodha_os.server
pause
