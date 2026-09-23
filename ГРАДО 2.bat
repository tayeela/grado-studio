@echo off
chcp 65001 >nul
rem ГРАДО 2 on Windows without an installer: double-click. First start creates %LOCALAPPDATA%\GRADO2\venv.
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\GRADO2\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Первый запуск: готовлю окружение ГРАДО 2...
  py -3 -m venv "%VENV%" || python -m venv "%VENV%" || (echo Нужен Python 3.10+ с python.org & pause & exit /b 1)
)
"%VENV%\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r apps\grado2\requirements.txt
"%VENV%\Scripts\python.exe" apps\grado2\server.py
