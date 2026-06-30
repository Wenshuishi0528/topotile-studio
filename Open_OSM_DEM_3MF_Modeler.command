#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/apple/Downloads/osm_dem_3mf_modeler"
PORT="8000"
URL="http://127.0.0.1:${PORT}/"

cd "$PROJECT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

echo "Checking Python dependencies..."
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
PY
then
  echo "Installing project dependencies..."
  ".venv/bin/python" -m pip install -r requirements.txt
fi

if lsof -nP -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "The app is already running at ${URL}"
  open "$URL"
  exit 0
fi

echo "Starting TopoTile Studio..."
".venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

for i in {1..80}; do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "Opening ${URL}"
    open "$URL"
    echo ""
    echo "Keep this Terminal window open while using the app."
    echo "Close this window, or press Ctrl+C, to stop the local server."
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 0.25
done

echo "The server did not become ready in time."
echo "Check the messages above for the error."
kill "$SERVER_PID" >/dev/null 2>&1 || true
exit 1
