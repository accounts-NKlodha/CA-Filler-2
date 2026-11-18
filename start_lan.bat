@echo off
rem Lodha OS for the whole office network: other computers open http://<this-computer-name>:8750
cd /d "%~dp0"
python -m lodha_os.server --lan
pause
