@echo off
rem Launcher for export_chat.py
rem Uses the Python bundled with AutoClaw, so no system install is required.

setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "SCRIPT=%~dp0export_chat.py"
set "PY="

if exist "%USERPROFILE%\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe" set "PY=%USERPROFILE%\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe"
if not defined PY if exist "%USERPROFILE%\AppData\Local\Programs\AutoClaw\resources\vendor\python\python.exe" set "PY=%USERPROFILE%\AppData\Local\Programs\AutoClaw\resources\vendor\python\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\AutoClaw2\resources\vendor\python\python.exe" set "PY=%LOCALAPPDATA%\Programs\AutoClaw2\resources\vendor\python\python.exe"
if not defined PY if exist "%PROGRAMFILES%\AutoClaw2\resources\vendor\python\python.exe" set "PY=%PROGRAMFILES%\AutoClaw2\resources\vendor\python\python.exe"
if not defined PY if exist "%USERPROFILE%\AppData\Roaming\AutoClaw-oversea-official\toolchain\python\Python313\python.exe" set "PY=%USERPROFILE%\AppData\Roaming\AutoClaw-oversea-official\toolchain\python\Python313\python.exe"

if not defined PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PY echo %%P | find /i "WindowsApps" >nul || set "PY=%%P"
  )
)

if not defined PY (
  echo [ERROR] Python not found.
  echo Install it with:  winget install Python.Python.3.13
  echo Then turn off the Store alias: Settings - Apps - Advanced app settings - App execution aliases - python.exe
  pause
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo [ERROR] export_chat.py not found next to this .bat
  echo Rename export_chat_v4.py to export_chat.py and try again.
  pause
  exit /b 1
)

echo Using: %PY%
echo.
"%PY%" "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"
echo.
if "%~1"=="" pause
exit /b %RC%
