#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t osm-dem-3mf-modeler .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" osm-dem-3mf-modeler
