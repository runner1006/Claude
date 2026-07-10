#!/usr/bin/env python3
"""OEFB-Webservice: Dashboard + JSON-API + Remote-MCP + Daten-Upload.

Routen
------
GET  /                    Dashboard (statisch)
GET  /data/<name>         Datendateien; liegt <name>.gz auf der Disk, wird sie
                          mit Content-Encoding: gzip ausgeliefert (klein & schnell)
GET  /api/health          Status + Datenbestand
GET  /api/search?q=       Spielersuche (FTS)
GET  /api/player/{id}     Spielerprofil komplett
GET  /api/top             Rating-Bestenliste (Parameter wie MCP top_ratings)
POST /admin/upload?name=  Daten-Upload (Bearer ADMIN_TOKEN); atomisch, fuer
                          oefb.sqlite und Dashboard-Datendateien
/mcp                      Remote-MCP (streamable HTTP, Bearer MCP_TOKEN)

Env: OEFB_DATA_DIR (Default ./data), OEFB_DB, ADMIN_TOKEN, MCP_TOKEN, PUBLIC_MODE
Start lokal:
    uv run --python 3.12 --with "fastapi,uvicorn,mcp" \
        uvicorn server.app:app --port 8010
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oefb_mcp  # noqa: E402  (stellt FastMCP-Server + _rows bereit)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("OEFB_DATA_DIR", os.path.join(ROOT, "data"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")

# DB-Pfad fuer oefb_mcp auf die Disk umbiegen
oefb_mcp.DB = os.environ.get("OEFB_DB", os.path.join(DATA_DIR, "oefb.sqlite"))

mcp = oefb_mcp.mcp
mcp.settings.streamable_http_path = "/"          # -> unter /mcp gemountet
mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="ÖFB Daten-Service", lifespan=lifespan)


class MCPAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/mcp") and MCP_TOKEN:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {MCP_TOKEN}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(MCPAuth)
app.mount("/mcp", mcp_app)


@app.post("/mcp")
def mcp_no_slash():
    # Starlette-Mount matcht nur /mcp/ - Redirect erhaelt Methode+Body (307)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/mcp/", status_code=307)

_MIME = {".json": "application/json", ".csv": "text/csv; charset=utf-8",
         ".sqlite": "application/octet-stream", ".txt": "text/plain"}
_ALLOWED_STATIC = {"dashboard.html", "index.html", "histogram-range.js"}


@app.get("/")
def root():
    return FileResponse(os.path.join(ROOT, "dashboard.html"), media_type="text/html")


@app.get("/{name}")
def static_file(name: str):
    if name not in _ALLOWED_STATIC:
        raise HTTPException(404)
    mt = "application/javascript" if name.endswith(".js") else "text/html"
    return FileResponse(os.path.join(ROOT, name), media_type=mt)


@app.get("/data/{name}")
def data_file(name: str, request: Request):
    if "/" in name or ".." in name:
        raise HTTPException(404)
    base = os.path.join(DATA_DIR, name)
    ext = os.path.splitext(name)[1]
    mt = _MIME.get(ext, "application/octet-stream")
    gz = base + ".gz"
    if os.path.exists(gz):                       # vor-gezippt -> transparent
        etag = f'W/"{int(os.path.getmtime(gz))}-{os.path.getsize(gz)}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304)
        return FileResponse(gz, media_type=mt, headers={
            "Content-Encoding": "gzip", "ETag": etag, "Vary": "Accept-Encoding"})
    if os.path.exists(base):
        return FileResponse(base, media_type=mt)
    raise HTTPException(404)


@app.get("/api/health")
def health():
    try:
        n = {t: oefb_mcp._rows(f"SELECT COUNT(*) n FROM {t}")[0]["n"]
             for t in ("matches", "players", "appearances", "ratings")}
        ver = oefb_mcp._rows("SELECT MAX(iso_date) d FROM matches")[0]["d"]
        return {"status": "ok", "counts": n, "latest_match": ver,
                "db_mtime": int(os.path.getmtime(oefb_mcp.DB))}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@app.get("/api/search")
def api_search(q: str, limit: int = 20):
    return json.loads(oefb_mcp.search_players(q, limit=limit))


@app.get("/api/player/{player_id}")
def api_player(player_id: str):
    return json.loads(oefb_mcp.get_player(player_id))


@app.get("/api/top")
def api_top(birth_year: int | None = None, competition: str | None = None,
            metric: str = "total", min_minutes: int = 270, limit: int = 25):
    return json.loads(oefb_mcp.top_ratings(birth_year, competition, metric,
                                           min_minutes, limit))


@app.post("/admin/upload")
async def upload(request: Request, name: str):
    if not ADMIN_TOKEN or request.headers.get("authorization") != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(401)
    if "/" in name or ".." in name:
        raise HTTPException(400)
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, name)
    tmp = dest + ".uploading"
    h = hashlib.sha256()
    size = 0
    with open(tmp, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk); h.update(chunk); size += len(chunk)
    os.replace(tmp, dest)                        # atomisch aktivieren
    return {"ok": True, "name": name, "bytes": size, "sha256": h.hexdigest()}
