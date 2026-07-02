@echo off
setlocal EnableExtensions
chcp 65001 >nul

title TopoTile Studio - 3D地图工坊 Windows Start

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"
set "PYTHON_DOWNLOAD_URL=https://www.python.org/downloads/windows/"

cd /d "%~dp0"

echo.
echo TopoTile Studio / 3D Map Workshop startup check
echo TopoTile Studio / 3D地图工坊 启动检查
echo.
echo Checking for compatible Python 3.11/3.12. (1/3)
echo 正在检查可用的 Python 3.11/3.12。（1/3）

call :FindCompatiblePython
if not defined PYTHON_EXE (
  call :AskRuntimeInstall
  if errorlevel 1 (
    call :ManualPythonInstructions
    exit /b 1
  )

  call :InstallPythonWithWinget
  if errorlevel 1 (
    call :ManualPythonInstructions
    exit /b 1
  )

  call :FindCompatiblePython
  if not defined PYTHON_EXE (
    call :ManualPythonInstructions
    exit /b 1
  )
)

call :EnsureVirtualEnvironment
if errorlevel 1 exit /b 1

echo.
echo Checking TopoTile Studio / 3D Map Workshop dependencies. (3/3)
echo 正在检查 TopoTile Studio / 3D地图工坊 所需组件。（3/3）
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, multipart, requests, numpy, shapely, pyproj, trimesh, rasterio, scipy, networkx, lxml" >nul 2>nul
if errorlevel 1 (
  echo Installing TopoTile Studio / 3D Map Workshop dependencies. This may take a few minutes. (3/3)
  echo 正在安装 TopoTile Studio / 3D地图工坊 所需组件，可能需要几分钟。（3/3）
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Failed to upgrade pip.
    echo pip 升级失败。
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies.
    echo 依赖安装失败。
    pause
    exit /b 1
  )
)

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo TopoTile Studio / 3D Map Workshop is already running at %URL%
  echo TopoTile Studio / 3D地图工坊 已经在 %URL% 运行。
  start "" "%URL%"
  exit /b 0
)

echo Starting TopoTile Studio / 3D Map Workshop...
echo 正在启动 TopoTile Studio / 3D地图工坊...
start "TopoTile Studio Server" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

for /l %%I in (1,1,80) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 (
    echo Opening %URL%
    echo 正在打开 %URL%
    start "" "%URL%"
    echo.
    echo Keep the "TopoTile Studio Server" window open while using the app.
    echo 使用软件时请保持 "TopoTile Studio Server" 窗口打开。
    echo Close that server window, or press Ctrl+C inside it, to stop the local server.
    echo 关闭该服务器窗口，或在窗口内按 Ctrl+C，即可停止本地服务器。
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)

echo The server did not become ready in time.
echo 服务器未能及时启动。
echo Check the "TopoTile Studio Server" window for the error message.
echo 请查看 "TopoTile Studio Server" 窗口中的错误信息。
pause
exit /b 1

:FindCompatiblePython
set "PYTHON_EXE="
set "PYTHON_ARGS="

py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3.12"
  goto :eof
)

py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3.11"
  goto :eof
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12)] else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=python"
  goto :eof
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  "%LocalAppData%\Programs\Python\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto :eof
  )
)

if exist "%ProgramFiles%\Python312\python.exe" (
  "%ProgramFiles%\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    goto :eof
  )
)

goto :eof

:AskRuntimeInstall
echo.
echo No compatible Python 3.11/3.12 was found.
echo 未检测到可用的 Python 3.11/3.12。
echo.
echo Install Python 3.12 automatically with winget? Type yes or no. (1/3)
echo 是否使用 winget 自动安装 Python 3.12？请输入 yes 或 no。（1/3）
set /p "ANSWER=> "
if /I "%ANSWER%"=="yes" exit /b 0
if /I "%ANSWER%"=="y" exit /b 0
if /I "%ANSWER%"=="no" exit /b 1
if /I "%ANSWER%"=="n" exit /b 1
echo Please type yes or no.
echo 请输入 yes 或 no。
goto :AskRuntimeInstall

:InstallPythonWithWinget
where winget >nul 2>nul
if errorlevel 1 (
  echo.
  echo winget was not found, so automatic Python installation is unavailable.
  echo 未检测到 winget，因此无法自动安装 Python。
  exit /b 1
)

echo.
echo Installing Python 3.12 with winget. This may take a few minutes. (2/3)
echo 正在通过 winget 安装 Python 3.12，可能需要几分钟。（2/3）
echo Windows may show an installer or permission prompt. This is normal.
echo Windows 可能会显示安装程序或权限提示，这是正常现象。
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo Python installation failed.
  echo Python 安装失败。
  exit /b 1
)
exit /b 0

:EnsureVirtualEnvironment
set "VENV_OK="
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12)] else 1)" >nul 2>nul
  if not errorlevel 1 set "VENV_OK=1"
)

if not defined VENV_OK (
  if exist ".venv" (
    echo Existing virtual environment uses an unsupported Python version. Recreating it...
    echo 现有虚拟环境使用了不推荐的 Python 版本，正在重新创建...
    rmdir /s /q ".venv"
  ) else (
    echo Creating Python virtual environment...
    echo 正在创建 Python 虚拟环境...
  )
  "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    echo 创建虚拟环境失败。
    pause
    exit /b 1
  )
)
exit /b 0

:ManualPythonInstructions
echo.
echo Automatic setup was cancelled or could not finish.
echo 自动安装已取消或未能完成。
echo.
echo Please install Python 3.12 manually, then run this launcher again:
echo 请手动安装 Python 3.12，然后重新运行这个启动文件：
echo %PYTHON_DOWNLOAD_URL%
echo.
echo During installation, enable "Add python.exe to PATH" if the installer shows that option.
echo 安装时如果看到 "Add python.exe to PATH" 选项，请勾选。
start "" "%PYTHON_DOWNLOAD_URL%"
pause
exit /b 0
