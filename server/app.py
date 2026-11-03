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
GET  /api/profile/{id}    Fertiges Dashboard-Profil (vorberechnet, build_dashboard.py)
GET  /api/match/{id}      Spiel mit Aufstellungen (Minuten) und Events
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

import gzip

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
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
app.add_middleware(GZipMiddleware, minimum_size=1000)   # API-JSON komprimiert ausliefern
app.mount("/mcp", mcp_app)


@app.post("/mcp")
def mcp_no_slash():
    # Starlette-Mount matcht nur /mcp/ - Redirect erhaelt Methode+Body (307)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/mcp/", status_code=307)

_MIME = {".json": "application/json", ".csv": "text/csv; charset=utf-8",
         ".sqlite": "application/octet-stream", ".txt": "text/plain"}
_ALLOWED_STATIC = {"dashboard.html", "index.html", "histogram-range.js"}
# /data/* liefert nur die vorberechneten Dashboard-Dateien. Alles andere im Datenordner (oefb.sqlite,
# grosse Roh-Exporte) bleibt privat - sonst wuerde die GZip-Middleware z. B. die 160-MB-DB je Request
# komplett komprimieren (~10 s CPU) und jeder koennte sie herunterladen.
_ALLOWED_DATA = {"scout.json", "matches_index.json"}


_NOCACHE = {"Cache-Control": "no-cache"}   # Browser fragt mit ETag nach -> 304 wenn unveraendert


def _file_etag(path: str) -> str:
    st = os.stat(path)
    return f'W/"{int(st.st_mtime)}-{st.st_size}"'


def _static(path: str, mt: str, request: Request):
    """Statische Datei mit ETag; If-None-Match-Treffer -> 304 (Wiederbesuch laedt nichts)."""
    if not os.path.exists(path):
        raise HTTPException(404)
    etag = _file_etag(path)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, **_NOCACHE})
    return FileResponse(path, media_type=mt, headers={"ETag": etag, **_NOCACHE})


@app.get("/")
def root(request: Request):
    return _static(os.path.join(ROOT, "dashboard.html"), "text/html", request)


@app.get("/{name}")
def static_file(name: str, request: Request):
    if name not in _ALLOWED_STATIC:
        raise HTTPException(404)
    mt = "application/javascript" if name.endswith(".js") else "text/html"
    return _static(os.path.join(ROOT, name), mt, request)


@app.get("/data/{name}")
def data_file(name: str, request: Request):
    if name not in _ALLOWED_DATA:
        raise HTTPException(404)
    base = os.path.join(DATA_DIR, name)
    ext = os.path.splitext(name)[1]
    mt = _MIME.get(ext, "application/octet-stream")
    gz = base + ".gz"
    if os.path.exists(gz):                       # vor-gezippt -> transparent
        etag = _file_etag(gz)
        headers = {"ETag": etag, "Vary": "Accept-Encoding", **_NOCACHE}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        if "gzip" in request.headers.get("accept-encoding", ""):
            return FileResponse(gz, media_type=mt, headers={"Content-Encoding": "gzip", **headers})
        if os.path.exists(base):                 # Client ohne gzip: Rohdatei ...
            return FileResponse(base, media_type=mt, headers=headers)
        with gzip.open(gz, "rb") as f:           # ... oder entpackt aus der .gz
            return Response(content=f.read(), media_type=mt, headers=headers)
    if os.path.exists(base):
        return _static(base, mt, request)
    raise HTTPException(404)


@app.get("/api/health")
def health():
    # Wichtig: auch OHNE Daten 200 liefern - sonst kommt der Service nie live,
    # und der erste Daten-Upload (der die DB erst bringt) waere unmoeglich.
    if not os.path.exists(oefb_mcp.DB):
        return {"status": "empty", "detail": "Noch keine Daten - Upload via update_all.py"}
    try:
        n = {t: oefb_mcp._rows(f"SELECT COUNT(*) n FROM {t}")[0]["n"]
             for t in ("matches", "players", "appearances", "ratings")}
        ver = oefb_mcp._rows("SELECT MAX(iso_date) d FROM matches")[0]["d"]
        out = {"status": "ok", "counts": n, "latest_match": ver,
               "db_mtime": int(os.path.getmtime(oefb_mcp.DB))}
        try:
            out["dashboard"] = {r["k"]: r["v"] for r in oefb_mcp._rows("SELECT k, v FROM dash_meta")}
        except Exception:  # noqa: BLE001  (DB ohne build_dashboard.py)
            out["dashboard"] = None
        return out
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


def _db_etag() -> str:
    try:
        return f'W/"db-{int(os.path.getmtime(oefb_mcp.DB))}"'
    except OSError:
        return 'W/"db-0"'


@app.get("/api/profile/{player_id}")
def api_profile(player_id: str, request: Request):
    """Vorberechnetes Profil (gzip-Blob aus dash_profile) - ohne Rechenarbeit zur Laufzeit."""
    if not player_id.isdigit():
        raise HTTPException(404)
    etag = _db_etag()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    try:
        rows = oefb_mcp._rows("SELECT gz FROM dash_profile WHERE player_id=?", (player_id,))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Profil-Tabelle fehlt (build_dashboard.py): {e}")
    if not rows:
        raise HTTPException(404, "Spieler nicht gefunden")
    blob = rows[0]["gz"]
    headers = {"ETag": etag, "Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", ""):
        headers["Content-Encoding"] = "gzip"
        return Response(content=blob, media_type="application/json", headers=headers)
    return Response(content=gzip.decompress(blob), media_type="application/json", headers=headers)


@app.get("/api/match/{match_id}")
def api_match(match_id: str, request: Request):
    """Spiel-Detail fuer den Matches-Tab: Aufstellungen (mit Minuten/Alter) + Events."""
    if not match_id.isdigit():
        raise HTTPException(404)
    etag = _db_etag()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    m = oefb_mcp._rows("SELECT * FROM matches WHERE match_id=?", (match_id,))
    if not m:
        raise HTTPException(404, "Spiel nicht gefunden")
    lineup = oefb_mcp._rows(
        """SELECT a.side, a.role, a.number, a.name, a.player_id, a.captain, a.minutes,
                  a.on_min, a.off_min, a.goals, a.position, p.birth_year
           FROM appearances a LEFT JOIN players p ON p.player_id=a.player_id
           WHERE a.match_id=? ORDER BY a.rowid""", (match_id,))
    events = oefb_mcp._rows(
        "SELECT type, minute_raw AS minute, team, player, player_out, detail "
        "FROM events WHERE match_id=? ORDER BY rowid", (match_id,))
    out = {"match": m[0], "lineup": {"home": [], "away": []}, "events": events}
    for a in lineup:
        if a["side"] in out["lineup"]:
            out["lineup"][a["side"]].append(a)
    return JSONResponse(out, headers={"ETag": etag, "Cache-Control": "no-cache"})


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
