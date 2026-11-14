# SPDX-License-Identifier: GPL-3.0-or-later
"""Exporta las playlists de Spotify a archivos TXT ("Canción - Artista", una por línea).

Cliente mínimo de la Web API hecho con la biblioteca estándar: flujo de autorización
con Client ID + Client Secret y un servidor local que recibe la redirección.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1/"
SCOPES = "playlist-read-private playlist-read-collaborative user-library-read"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
AUTH_TIMEOUT = 300  # segundos para aceptar en el navegador


class SpotifyError(Exception):
    """`code` es una clave corta que la interfaz traduce; `status` el código HTTP si lo hay."""

    def __init__(self, code: str, status: int = 0, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail


def _http(method: str, url: str, headers: dict, data: bytes | None) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SpotifyError("network", detail=str(getattr(exc, "reason", exc))) from exc


class Client:
    def __init__(self, client_id: str, client_secret: str, token: dict | None = None,
                 on_token: Callable[[dict], None] | None = None, http=_http,
                 redirect_uri: str = REDIRECT_URI, sleep=time.sleep):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.token = dict(token) if token else None
        self.redirect_uri = redirect_uri
        self._on_token = on_token
        self._http = http
        self._sleep = sleep

    # ── Autorización ──

    def authorize_url(self, state: str) -> str:
        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": state,
        })
        return f"{AUTH_URL}?{query}"

    def _token_request(self, fields: dict) -> dict:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        status, _headers, body = self._http(
            "POST", TOKEN_URL,
            {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode(fields).encode(),
        )
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if status != 200 or "access_token" not in data:
            error = data.get("error", "") if isinstance(data, dict) else ""
            code = "bad_credentials" if error in ("invalid_client", "invalid_request") else "auth_failed"
            if error == "invalid_grant":
                code = "session_expired"
            raise SpotifyError(code, status, str(data.get("error_description", "")) if isinstance(data, dict) else "")
        return data

    def _store(self, data: dict) -> None:
        previous = self.token or {}
        self.token = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token") or previous.get("refresh_token", ""),
            "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
            "client_id": self.client_id,
        }
        if self._on_token:
            self._on_token(dict(self.token))

    def exchange(self, code: str) -> None:
        self._store(self._token_request({
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
        }))

    def refresh(self) -> None:
        if not self.token or not self.token.get("refresh_token"):
            raise SpotifyError("session_expired")
        self._store(self._token_request({
            "grant_type": "refresh_token", "refresh_token": self.token["refresh_token"],
        }))

    def has_session(self) -> bool:
        """Hay una sesión guardada que corresponde a este Client ID."""
        return bool(self.token and self.token.get("refresh_token") and self.token.get("client_id") == self.client_id)

    # ── API ──

    def get(self, path: str, **params) -> dict:
        url = path if path.startswith("https://") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        refreshed = False
        for _attempt in range(6):
            if not self.token or self.token.get("expires_at", 0) - 30 < time.time():
                self.refresh()
                refreshed = True
            status, headers, body = self._http("GET", url, {"Authorization": f"Bearer {self.token['access_token']}"}, None)
            if status == 200:
                try:
                    return json.loads(body)
                except ValueError as exc:
                    raise SpotifyError("api", status, "invalid JSON") from exc
            if status == 401 and not refreshed:
                self.token["expires_at"] = 0
                continue
            if status == 429:
                wait = {k.lower(): v for k, v in headers.items()}.get("retry-after", "2")
                self._sleep(min(30, max(1, int(wait) if str(wait).isdigit() else 2)))
                continue
            if status in (500, 502, 503, 504):
                self._sleep(2)
                continue
            raise SpotifyError("forbidden" if status == 403 else "api", status)
        raise SpotifyError("api", 429)

    def paginate(self, page: dict):
        while page:
            yield from page.get("items") or []
            page = self.get(page["next"]) if page.get("next") else None


# ── Servidor local para la redirección ─────────────────────────────────────────

_DONE_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>music-dlp</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:18vh'>"
    "<h2>{title}</h2><p>{body}</p></body>"
)


def wait_for_code(redirect_uri: str, state: str, cancel: threading.Event, on_ready: Callable[[], None],
                  timeout: float = AUTH_TIMEOUT) -> str:
    """Abre el puerto de la Redirect URI, avisa con `on_ready` y espera el código de Spotify."""
    target = urllib.parse.urlparse(redirect_uri)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nombre impuesto por http.server)
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != target.path or query.get("state", [""])[0] != state:
                self.send_response(404)
                self.end_headers()
                return
            if "code" in query:
                result["code"] = query["code"][0]
                page = _DONE_PAGE.format(title="✔ music-dlp", body="Listo, ya podés cerrar esta pestaña. / Done, you can close this tab.")
            else:
                result["error"] = query.get("error", ["denied"])[0]
                page = _DONE_PAGE.format(title="✘ music-dlp", body="Spotify no autorizó el acceso. / Spotify did not grant access.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode())

        def log_message(self, *_args):
            pass

    try:
        server = HTTPServer((target.hostname or "127.0.0.1", target.port or 80), Handler)
    except OSError as exc:
        raise SpotifyError("port_busy", detail=str(target.port)) from exc
    server.timeout = 0.3
    try:
        on_ready()
        deadline = time.monotonic() + timeout
        while not result:
            if cancel.is_set():
                raise SpotifyError("cancelled")
            if time.monotonic() > deadline:
                raise SpotifyError("auth_timeout")
            server.handle_request()
    finally:
        server.server_close()
    if "code" not in result:
        raise SpotifyError("auth_denied", detail=result.get("error", ""))
    return result["code"]


def login(client: Client, cancel: threading.Event, open_url: Callable[[str], None]) -> None:
    """Abre el navegador para autorizar la app y deja el token en el cliente."""
    state = secrets.token_urlsafe(16)
    code = wait_for_code(client.redirect_uri, state, cancel, lambda: open_url(client.authorize_url(state)))
    client.exchange(code)


# ── Exportación ────────────────────────────────────────────────────────────────

@dataclass
class Exported:
    name: str
    path: Path
    songs: int


def safe_filename(name: str) -> str:
    """Quita los caracteres que no valen en nombres de archivo."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return clean[:150] or "untitled"


def unique_path(folder: Path, name: str, used: set[str]) -> Path:
    """Evita que dos playlists con el mismo nombre se pisen."""
    candidate, n = name, 2
    while candidate.lower() in used:
        candidate = f"{name} ({n})"
        n += 1
    used.add(candidate.lower())
    return folder / f"{candidate}.txt"


def format_track(track: dict) -> str:
    """"Canción - Artista" (varios artistas separados por comas)."""
    artists = ", ".join(a["name"] for a in track.get("artists") or [] if a.get("name"))
    if not artists and track.get("show"):  # episodios de podcast
        artists = track["show"].get("name", "")
    return f"{track['name']} - {artists}" if artists else track["name"]


def playlist_tracks(client: Client, playlist_id: str) -> list[str]:
    try:
        page = client.get(f"playlists/{playlist_id}/items", limit=50)  # endpoint actual
    except SpotifyError as exc:
        if exc.code not in ("api", "forbidden"):
            raise
        page = client.get(f"playlists/{playlist_id}/tracks", limit=100)  # endpoint anterior
    names = []
    for entry in client.paginate(page):
        track = entry.get("item") or entry.get("track")
        if track and track.get("name"):
            names.append(format_track(track))
    return names


def liked_tracks(client: Client) -> list[str]:
    page = client.get("me/tracks", limit=50)
    return [format_track(e["track"]) for e in client.paginate(page) if e.get("track") and e["track"].get("name")]


def _save(folder: Path, name: str, tracks: list[str], used: set[str]) -> Path:
    path = unique_path(folder, safe_filename(name), used)
    path.write_text("\n".join(tracks) + ("\n" if tracks else ""), encoding="utf-8")
    return path


def export(client: Client, folder: Path, own_only: bool, include_liked: bool, liked_name: str,
           cancel: threading.Event, emit: Callable[..., None]) -> list[Exported]:
    """Escribe un TXT por playlist en `folder`. Avisa con emit(kind, **datos)."""
    me = client.get("me")["id"]
    folder.mkdir(parents=True, exist_ok=True)
    playlists = [p for p in client.paginate(client.get("me/playlists", limit=50)) if p]
    if own_only:
        playlists = [p for p in playlists if (p.get("owner") or {}).get("id") == me]
    emit("found", n=len(playlists))

    done: list[Exported] = []
    used: set[str] = set()
    for playlist in playlists:
        if cancel.is_set():
            raise SpotifyError("cancelled")
        name = playlist.get("name") or "untitled"
        try:
            tracks = playlist_tracks(client, playlist["id"])
        except SpotifyError as exc:
            if exc.code in ("cancelled", "network", "session_expired", "bad_credentials"):
                raise
            emit("playlist_failed", name=name, status=exc.status)
            continue
        path = _save(folder, name, tracks, used)
        done.append(Exported(name, path, len(tracks)))
        emit("playlist_ok", name=name, n=len(tracks), file=path.name)
    if include_liked and not cancel.is_set():
        tracks = liked_tracks(client)
        path = _save(folder, liked_name, tracks, used)
        done.append(Exported(liked_name, path, len(tracks)))
        emit("playlist_ok", name=liked_name, n=len(tracks), file=path.name)
    return done
