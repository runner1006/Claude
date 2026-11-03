#!/bin/sh
# Lokaler Testserver fuer das Dashboard (Python 3.12 via uv, wie auf Render).
#   ./serve_local.sh [DATA_DIR] [PORT]
# DATA_DIR: Ordner mit oefb.sqlite + scout.json/matches_index.json (Default: ./data)
cd "$(dirname "$0")" || exit 1
export OEFB_DATA_DIR="${1:-$PWD/data}"
PORT="${2:-8010}"
exec uv run --python 3.12 --with "fastapi,uvicorn,mcp<2" \
  uvicorn server.app:app --host 127.0.0.1 --port "$PORT"
