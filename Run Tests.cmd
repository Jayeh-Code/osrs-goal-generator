@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows.ps1" -Action test
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
