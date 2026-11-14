# SPDX-License-Identifier: GPL-3.0-or-later
"""Carga yt-dlp (el incluido o uno más nuevo bajado por el usuario) y lo actualiza desde PyPI.

La actualización solo corre cuando el usuario la pide: baja las ruedas (wheels) de
yt-dlp y yt-dlp-ejs por HTTPS, comprueba su SHA-256 contra el que publica PyPI y las
descomprime en <datos>/yt-dlp. No se ejecuta nada de lo descargado durante la actualización.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import re
import shutil
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import settings

PYPI = "https://pypi.org/pypi/{name}/json"
PYPI_VERSION = "https://pypi.org/pypi/{name}/{version}/json"
MAX_WHEEL = 40 * 1024 * 1024
_lock = threading.Lock()
_module = None


class UpdateError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def user_dir() -> Path:
    return settings.data_dir() / "yt-dlp"


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text))


def user_version() -> str:
    """Versión del yt-dlp bajado por el usuario, o "" si no hay."""
    try:
        text = (user_dir() / "yt_dlp" / "version.py").read_text("utf-8")
    except OSError:
        return ""
    found = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
    return found.group(1) if found else ""


def _purge() -> None:
    for name in list(sys.modules):
        if name.split(".")[0] in ("yt_dlp", "yt_dlp_ejs"):
            del sys.modules[name]
    importlib.invalidate_caches()


def module(reload: bool = False):
    """Devuelve el módulo yt_dlp más nuevo entre el incluido y el del usuario."""
    global _module
    with _lock:
        if _module is not None and not reload:
            return _module
        path = str(user_dir())
        if path in sys.path:
            sys.path.remove(path)
        _purge()
        import yt_dlp

        mine = user_version()
        if mine and version_tuple(mine) > version_tuple(yt_dlp.version.__version__):
            _purge()
            sys.path.insert(0, path)
            try:
                import yt_dlp
            except Exception:  # copia rota: volver al incluido
                sys.path.remove(path)
                _purge()
                import yt_dlp
        _module = yt_dlp
        return _module


def current_version() -> str:
    return module().version.__version__


def _fetch(url: str, limit: int = MAX_WHEEL) -> bytes:
    if not url.startswith("https://"):
        raise UpdateError("network", "URL sin HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "music-dlp"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(limit + 1)
    except OSError as exc:
        raise UpdateError("network", str(getattr(exc, "reason", exc))) from exc
    if len(data) > limit:
        raise UpdateError("invalid", "archivo demasiado grande")
    return data


def pick_wheel(meta: dict) -> tuple[str, str]:
    """(url, sha256) de la rueda universal de una versión de PyPI."""
    for item in meta.get("urls") or []:
        if item.get("packagetype") == "bdist_wheel" and item.get("filename", "").endswith("-none-any.whl"):
            return item["url"], item["digests"]["sha256"]
    raise UpdateError("invalid", "PyPI no publica una rueda universal")


def ejs_pin(meta: dict) -> str:
    """Versión de yt-dlp-ejs que pide esta versión de yt-dlp ("" si no pide ninguna)."""
    for requirement in (meta.get("info") or {}).get("requires_dist") or []:
        found = re.match(r"yt-dlp-ejs\s*==\s*([\w.]+)", requirement)
        if found:
            return found.group(1)
    return ""


def _unpack(data: bytes, sha256: str, target: Path) -> None:
    if hashlib.sha256(data).hexdigest() != sha256:
        raise UpdateError("checksum")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            name = member.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise UpdateError("invalid", name)
        archive.extractall(target)


def update(emit: Callable[..., None], fetch: Callable[[str], bytes] = _fetch) -> str:
    """Baja el último yt-dlp si es más nuevo que el que se usa. Devuelve la versión en uso."""
    current = current_version()
    try:
        meta = json.loads(fetch(PYPI.format(name="yt-dlp")))
        latest = meta["info"]["version"]
    except (ValueError, KeyError, TypeError) as exc:
        raise UpdateError("invalid", str(exc)) from exc
    emit("versions", current=current, latest=latest)
    if version_tuple(latest) <= version_tuple(current):
        return current

    wheels = [pick_wheel(meta)]
    pin = ejs_pin(meta)
    if pin:
        try:
            wheels.append(pick_wheel(json.loads(fetch(PYPI_VERSION.format(name="yt-dlp-ejs", version=pin)))))
        except ValueError as exc:
            raise UpdateError("invalid", str(exc)) from exc

    final = user_dir()
    fresh = final.with_name("yt-dlp.new")
    shutil.rmtree(fresh, ignore_errors=True)
    fresh.mkdir(parents=True)
    try:
        for url, sha256 in wheels:
            emit("downloading", file=url.rsplit("/", 1)[-1])
            _unpack(fetch(url), sha256, fresh)
        if not (fresh / "yt_dlp" / "version.py").is_file():
            raise UpdateError("invalid", "la rueda no contiene yt_dlp")
        shutil.rmtree(final, ignore_errors=True)
        fresh.rename(final)
    finally:
        shutil.rmtree(fresh, ignore_errors=True)
    return module(reload=True).version.__version__
