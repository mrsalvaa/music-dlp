# SPDX-License-Identifier: GPL-3.0-or-later
import json
import threading
import time
import urllib.parse
import urllib.request

import pytest

from music_dlp import spotify


class FakeApi:
    """Responde como la Web API de Spotify a partir de un diccionario url -> respuesta."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.token_calls = []

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url))
        if url == spotify.TOKEN_URL:
            fields = dict(urllib.parse.parse_qsl(data.decode()))
            self.token_calls.append(fields)
            answer = self.routes.get("token", (200, {"access_token": "nuevo", "expires_in": 3600, "refresh_token": "r2"}))
            return answer[0], {}, json.dumps(answer[1]).encode()
        answer = self.routes[url.removeprefix(spotify.API)]
        if isinstance(answer, list):
            answer = answer.pop(0)
        status, headers_out, body = answer if len(answer) == 3 else (answer[0], {}, answer[1])
        return status, headers_out, json.dumps(body).encode()


def client(routes, token=None, **kw):
    api = FakeApi(routes)
    token = token if token is not None else {"access_token": "t", "refresh_token": "r", "expires_at": time.time() + 3600, "client_id": "id"}
    return spotify.Client("id", "secret", token or None, http=api, sleep=lambda _s: None, **kw), api


def track(name, *artists):
    return {"name": name, "artists": [{"name": a} for a in artists]}


def test_format_track():
    assert spotify.format_track(track("Under Pressure", "Queen", "David Bowie")) == "Under Pressure - Queen, David Bowie"
    assert spotify.format_track({"name": "Ep 1", "artists": [], "show": {"name": "Podcast"}}) == "Ep 1 - Podcast"
    assert spotify.format_track({"name": "Solo"}) == "Solo"


def test_safe_filename_and_unique_path(tmp_path):
    assert spotify.safe_filename('a/b:c?') == "a_b_c_"
    used = set()
    assert spotify.unique_path(tmp_path, "Rock", used).name == "Rock.txt"
    assert spotify.unique_path(tmp_path, "rock", used).name == "rock (2).txt"


def test_authorize_url_has_scopes_and_state():
    c, _ = client({})
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(c.authorize_url("xyz")).query))
    assert query["client_id"] == "id" and query["state"] == "xyz"
    assert query["redirect_uri"] == spotify.REDIRECT_URI and "playlist-read-private" in query["scope"]


def test_expired_token_is_refreshed_and_reported():
    saved = []
    c, api = client({"me": (200, {"id": "yo"})}, token={"access_token": "viejo", "refresh_token": "r", "expires_at": 0, "client_id": "id"}, on_token=saved.append)
    assert c.get("me") == {"id": "yo"}
    assert api.token_calls == [{"grant_type": "refresh_token", "refresh_token": "r"}]
    assert saved[0]["access_token"] == "nuevo" and saved[0]["refresh_token"] == "r2" and saved[0]["client_id"] == "id"


def test_refresh_keeps_old_refresh_token_when_not_rotated():
    c, _ = client({"token": (200, {"access_token": "n", "expires_in": 10}), "me": (200, {})}, token={"access_token": "v", "refresh_token": "r", "expires_at": 0})
    c.get("me")
    assert c.token["refresh_token"] == "r"


def test_bad_credentials_and_expired_session():
    c, _ = client({"token": (400, {"error": "invalid_client"})}, token={"access_token": "v", "refresh_token": "r", "expires_at": 0})
    with pytest.raises(spotify.SpotifyError) as err:
        c.get("me")
    assert err.value.code == "bad_credentials"
    c, _ = client({"token": (400, {"error": "invalid_grant"})}, token={"access_token": "v", "refresh_token": "r", "expires_at": 0})
    with pytest.raises(spotify.SpotifyError) as err:
        c.get("me")
    assert err.value.code == "session_expired"


def test_rate_limit_is_retried_and_403_is_forbidden():
    c, api = client({"me": [(429, {"Retry-After": "1"}, {}), (200, {}, {"id": "yo"})], "x": (403, {})})
    assert c.get("me") == {"id": "yo"}
    with pytest.raises(spotify.SpotifyError) as err:
        c.get("x")
    assert (err.value.code, err.value.status) == ("forbidden", 403)


def test_has_session_requires_same_client_id():
    c, _ = client({})
    assert c.has_session()
    c.client_id = "otro"
    assert not c.has_session()


def test_export_writes_one_txt_per_playlist(tmp_path):
    routes = {
        "me": (200, {"id": "yo"}),
        "me/playlists?limit=50": (200, {"items": [
            {"id": "p1", "name": "Rock", "owner": {"id": "yo"}},
            {"id": "p2", "name": "Rock", "owner": {"id": "otro"}},
            {"id": "p3", "name": "Daily Mix", "owner": {"id": "spotify"}},
        ], "next": None}),
        "playlists/p1/items?limit=50": (200, {"items": [{"item": track("Uno", "A")}], "next": spotify.API + "p1-pagina2"}),
        "p1-pagina2": (200, {"items": [{"track": track("Dos", "B", "C")}, {"item": None}], "next": None}),
        "playlists/p2/items?limit=50": (404, {}),
        "playlists/p2/tracks?limit=100": (200, {"items": [{"track": track("Tres", "D")}], "next": None}),
        "playlists/p3/items?limit=50": (403, {}),
        "playlists/p3/tracks?limit=100": (403, {}),
        "me/tracks?limit=50": (200, {"items": [{"track": track("Fav", "E")}], "next": None}),
    }
    c, _ = client(routes)
    events = []
    done = spotify.export(c, tmp_path, False, True, "Me gusta", threading.Event(), lambda k, **d: events.append((k, d)))
    assert [(e.name, e.path.name, e.songs) for e in done] == [("Rock", "Rock.txt", 2), ("Rock", "Rock (2).txt", 1), ("Me gusta", "Me gusta.txt", 1)]
    assert (tmp_path / "Rock.txt").read_text() == "Uno - A\nDos - B, C\n"
    assert ("playlist_failed", {"name": "Daily Mix", "status": 403}) in events
    assert events[0] == ("found", {"n": 3})


def test_export_own_only_without_liked(tmp_path):
    routes = {
        "me": (200, {"id": "yo"}),
        "me/playlists?limit=50": (200, {"items": [{"id": "p1", "name": "Mía", "owner": {"id": "yo"}}, {"id": "p2", "name": "Ajena", "owner": {"id": "otro"}}]}),
        "playlists/p1/items?limit=50": (200, {"items": []}),
    }
    c, _ = client(routes)
    done = spotify.export(c, tmp_path, True, False, "Liked", threading.Event(), lambda *_a, **_k: None)
    assert [e.name for e in done] == ["Mía"] and (tmp_path / "Mía.txt").read_text() == ""


def test_export_can_be_cancelled(tmp_path):
    routes = {"me": (200, {"id": "yo"}), "me/playlists?limit=50": (200, {"items": [{"id": "p1", "name": "A", "owner": {"id": "yo"}}]})}
    c, _ = client(routes)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(spotify.SpotifyError) as err:
        spotify.export(c, tmp_path, False, True, "Liked", cancel, lambda *_a, **_k: None)
    assert err.value.code == "cancelled"


def _callback(port, query, results):
    def go():
        try:
            results.append(urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?{query}", timeout=5).status)
        except Exception as exc:  # 404 esperado en un caso
            results.append(getattr(exc, "code", str(exc)))
    return go


def test_wait_for_code_checks_state_and_returns_code():
    port, results = 18931, []
    uri = f"http://127.0.0.1:{port}/callback"

    def ready():
        threading.Thread(target=lambda: (_callback(port, "code=malo&state=otro", results)(), _callback(port, "code=abc&state=s1", results)())).start()

    assert spotify.wait_for_code(uri, "s1", threading.Event(), ready, timeout=10) == "abc"
    time.sleep(0.2)
    assert results == [404, 200]


def test_wait_for_code_denied_and_cancelled():
    port = 18932
    uri = f"http://127.0.0.1:{port}/callback"
    with pytest.raises(spotify.SpotifyError) as err:
        spotify.wait_for_code(uri, "s", threading.Event(), lambda: threading.Thread(target=_callback(port, "error=access_denied&state=s", [])).start(), timeout=10)
    assert err.value.code == "auth_denied"
    cancel = threading.Event()
    with pytest.raises(spotify.SpotifyError) as err:
        spotify.wait_for_code(uri, "s", cancel, cancel.set, timeout=10)
    assert err.value.code == "cancelled"
    with pytest.raises(spotify.SpotifyError) as err:
        spotify.wait_for_code(uri, "s", threading.Event(), lambda: None, timeout=0.1)
    assert err.value.code == "auth_timeout"
