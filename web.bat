@echo off
setlocal
cd /d "%~dp0"
start "Finviz Weekly Scanner" ".venv\Scripts\pythonw.exe" -m finviz_scanner.webapp
