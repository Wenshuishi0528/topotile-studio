#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/apple/Downloads/osm_dem_3mf_modeler"
PORT="8000"
URL="http://127.0.0.1:${PORT}/"
PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/macos/"
HOMEBREW_URL="https://brew.sh/"

cd "$PROJECT_DIR"

say2() {
  echo "$1"
  echo "$2"
}

ask_yes_no() {
  local english="$1"
  local chinese="$2"
  local answer
  while true; do
    echo ""
    say2 "$english" "$chinese"
    printf "> "
    read -r answer
    answer="${answer:l}"
    case "$answer" in
      yes|y) return 0 ;;
      no|n) return 1 ;;
      *)
        say2 "Please type yes or no." "请输入 yes 或 no。"
        ;;
    esac
  done
}

manual_python_instructions() {
  echo ""
  say2 "Automatic setup was cancelled or could not finish." "自动安装已取消或未能完成。"
  echo ""
  say2 "Please install Python 3.12 manually, then run this launcher again:" "请手动安装 Python 3.12，然后重新运行这个启动文件："
  echo "$PYTHON_DOWNLOAD_URL"
  echo ""
  say2 "Homebrew can also install Python on macOS:" "macOS 也可以通过 Homebrew 安装 Python："
  echo "$HOMEBREW_URL"
  open "$PYTHON_DOWNLOAD_URL" >/dev/null 2>&1 || true
}

python_is_compatible() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12)} else 1)
PY
}

find_compatible_python() {
  local candidates=(
    python3.12
    python3.11
    python3
    /opt/homebrew/bin/python3.12
    /opt/homebrew/bin/python3.11
    /usr/local/bin/python3.12
    /usr/local/bin/python3.11
  )
  local cmd path
  for cmd in "${candidates[@]}"; do
    if [[ "$cmd" == /* ]]; then
      path="$cmd"
      [[ -x "$path" ]] || continue
    else
      path="$(command -v "$cmd" 2>/dev/null || true)"
      [[ -n "$path" ]] || continue
    fi
    if python_is_compatible "$path"; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

venv_is_compatible() {
  [[ -x ".venv/bin/python" ]] && python_is_compatible ".venv/bin/python"
}

setup_homebrew_path() {
  if [[ -x "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x "/usr/local/bin/brew" ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

install_python_macos() {
  setup_homebrew_path
  if ! command -v brew >/dev/null 2>&1; then
    if ask_yes_no \
      "Homebrew is required to install Python automatically on macOS. Install Homebrew automatically? Type yes or no. (2/3)" \
      "macOS 自动安装 Python 需要 Homebrew。是否自动安装 Homebrew？请输入 yes 或 no。（2/3）"; then
      echo ""
      say2 "The Homebrew installer may ask for your Mac password. This is normal." "Homebrew 安装程序可能会要求输入你的 Mac 密码，这是正常现象。"
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      setup_homebrew_path
    else
      manual_python_instructions
      exit 1
    fi
  fi

  echo ""
  say2 "Installing Python 3.12 with Homebrew. This may take a few minutes. (2/3)" "正在通过 Homebrew 安装 Python 3.12，可能需要几分钟。（2/3）"
  brew install python@3.12
}

echo ""
say2 "TopoTile Studio / 3D Map Workshop startup check" "TopoTile Studio / 3D地图工坊 启动检查"
echo ""
say2 "Checking for compatible Python 3.11/3.12. (1/3)" "正在检查可用的 Python 3.11/3.12。（1/3）"

PYTHON_CMD="$(find_compatible_python || true)"
if [[ -z "$PYTHON_CMD" ]]; then
  if ask_yes_no \
    "No compatible Python 3.11/3.12 was found. Install the required runtime automatically? Type yes or no. (1/3)" \
    "未检测到可用的 Python 3.11/3.12。是否自动安装所需运行环境？请输入 yes 或 no。（1/3）"; then
    install_python_macos
    PYTHON_CMD="$(find_compatible_python || true)"
    if [[ -z "$PYTHON_CMD" ]]; then
      manual_python_instructions
      exit 1
    fi
  else
    manual_python_instructions
    exit 1
  fi
fi

if ! venv_is_compatible; then
  if [[ -d ".venv" ]]; then
    say2 "Existing virtual environment uses an unsupported Python version. Recreating it..." "现有虚拟环境使用了不推荐的 Python 版本，正在重新创建..."
    rm -rf ".venv"
  else
    say2 "Creating Python virtual environment..." "正在创建 Python 虚拟环境..."
  fi
  "$PYTHON_CMD" -m venv .venv
fi

echo ""
say2 "Checking TopoTile Studio / 3D Map Workshop dependencies. (3/3)" "正在检查 TopoTile Studio / 3D地图工坊 所需组件。（3/3）"
if ! ".venv/bin/python" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import multipart
import requests
import numpy
import shapely
import pyproj
import trimesh
import rasterio
import scipy
import networkx
import lxml
PY
then
  say2 "Installing TopoTile Studio / 3D Map Workshop dependencies. This may take a few minutes. (3/3)" "正在安装 TopoTile Studio / 3D地图工坊 所需组件，可能需要几分钟。（3/3）"
  ".venv/bin/python" -m pip install --upgrade pip
  ".venv/bin/python" -m pip install -r requirements.txt
fi

if lsof -nP -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  say2 "TopoTile Studio / 3D Map Workshop is already running at ${URL}" "TopoTile Studio / 3D地图工坊 已经在 ${URL} 运行。"
  open "$URL"
  exit 0
fi

say2 "Starting TopoTile Studio / 3D Map Workshop..." "正在启动 TopoTile Studio / 3D地图工坊..."
".venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

for i in {1..80}; do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    say2 "Opening ${URL}" "正在打开 ${URL}"
    open "$URL"
    echo ""
    say2 "Keep this Terminal window open while using the app." "使用软件时请保持这个终端窗口打开。"
    say2 "Close this window, or press Ctrl+C, to stop the local server." "关闭这个窗口，或按 Ctrl+C，即可停止本地服务器。"
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 0.25
done

say2 "The server did not become ready in time." "服务器未能及时启动。"
say2 "Check the messages above for the error." "请查看上方错误信息。"
kill "$SERVER_PID" >/dev/null 2>&1 || true
exit 1
