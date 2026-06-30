@echo off
setlocal

title TopoTile Studio Windows Start

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"

cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python 3 was not found.
  echo Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
  echo During installation, enable "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

echo Checking Python dependencies...
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, multipart, requests, numpy, shapely, pyproj, trimesh, rasterio, scipy, networkx, lxml" >nul 2>nul
if errorlevel 1 (
  echo Installing project dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo TopoTile Studio is already running at %URL%
  start "" "%URL%"
  exit /b 0
)

echo Starting TopoTile Studio...
start "TopoTile Studio Server" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

for /l %%I in (1,1,80) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 (
    echo Opening %URL%
    start "" "%URL%"
    echo.
    echo Keep the "TopoTile Studio Server" window open while using the app.
    echo Close that server window, or press Ctrl+C inside it, to stop the local server.
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)

echo The server did not become ready in time.
echo Check the "TopoTile Studio Server" window for the error message.
pause
exit /b 1
