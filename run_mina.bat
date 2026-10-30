@echo off
setlocal
cd /d "%~dp0"
py -3.12 "%~dp0mina.py"
if errorlevel 1 pause
