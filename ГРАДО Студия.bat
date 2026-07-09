@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PORT=8643"
set "URL=http://localhost:%PORT%"

echo ============================================
echo   ГРАДО Студия — локальный запуск
echo ============================================

REM --- 1. рабочий Python 3 (py -3, затем python, затем python3) ---------------
set "PY="
py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python  -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=python"
if not defined PY python3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=python3"
if not defined PY (
    echo.
    echo   [!] Не найден Python 3.8+.
    echo       Установите его с https://www.python.org/downloads/
    echo       При установке отметьте "Add Python to PATH", затем запустите снова.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo   Python: %%v

REM --- 2. certifi (для HTTPS: карта-подложка, НСПД, OSM) ----------------------
%PY% -c "import certifi" >nul 2>nul
if errorlevel 1 (
    echo   Доустанавливаю компонент certifi ^(один раз^)...
    %PY% -m pip install --user --quiet certifi >nul 2>nul && echo   certifi установлен. || echo   [!] certifi не установился — карта-подложка может не грузиться ^(не критично^).
)

REM --- 3. сервер уже запущен? тогда просто открыть ---------------------------
%PY% -c "import urllib.request;urllib.request.urlopen('%URL%',timeout=1)" >nul 2>nul
if not errorlevel 1 (
    echo   Сервер уже запущен — открываю браузер.
    start "" "%URL%"
    exit /b 0
)

REM --- 4. запуск сервера (браузер откроется сам через --open) -----------------
echo   Запускаю сервер на %URL% ...
echo   Браузер откроется автоматически. Чтобы завершить работу — закройте это окно.
echo.
if "%~1"=="" (
    %PY% apps\studio\server.py %PORT% --open
) else (
    %PY% apps\studio\server.py %PORT% "%~1" --open
)

REM сюда попадаем, только если сервер завершился сам (обычно порт занят)
if errorlevel 1 (
    echo.
    echo   [!] Сервер завершился с ошибкой. Возможно, порт %PORT% занят
    echo       другой программой — закройте её и запустите снова.
    pause
)
endlocal
