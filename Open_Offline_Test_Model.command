#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$HOME/Downloads/TopoTile_Offline_Test_Model"

cd "$PROJECT_DIR"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

mkdir -p "$OUTPUT_DIR"

.venv/bin/python - "$OUTPUT_DIR" <<'PY'
from pathlib import Path
import sys

from city_modeler.pipeline import generate_sample

out = Path(sys.argv[1])
summary = generate_sample(out)
files = summary["files"]
print("Generated built-in offline test model:")
print(f"  3MF: {out / files['3mf']}")
print(f"  GLB: {out / files['glb']}")
print(f"  STL: {out / files['stl']}")
print(f"  Project JSON: {out / files['project']}")
print(f"  Triangles: {summary['validation_3mf']['triangles']}")
PY

open "$OUTPUT_DIR"
