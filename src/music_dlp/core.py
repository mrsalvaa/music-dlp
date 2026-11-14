# SPDX-License-Identifier: GPL-3.0-or-later
"""Motor de descargas: cada TXT es una playlist y cada playlist una carpeta.

No depende de Qt. Las descargas las hace un «backend» (yt-dlp en la app, uno falso
en los tests) y el motor se ocupa del orden, el paralelismo, lo ya descargado,
las copias entre playlists y el archivo de fallidas.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATE_FILE = ".music-dlp.json"
FAILED_NAMES = ("fallidas.txt", "failed.txt")


class Cancelled(Exception):
    pass


class DownloadFailed(Exception):
    """`code` es una clave que la interfaz traduce; `detail` el mensaje de yt-dlp."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class Options:
    dest: Path
    parallel: int = 4
    audio_format: str = "mp3"
    metadata: bool = True
    cover: bool = True
    skip_existing: bool = True
    failed_file: bool = True
    ytmusic: bool = True
    artist_folders: bool = False
    track_numbers: bool = False
    sponsorblock: bool = False
    failed_name: str = FAILED_NAMES[0]
    unknown_artist: str = "Desconocido"
    ffmpeg: str | None = None


@dataclass(frozen=True)
class Track:
    key: str  # identificador estable, p. ej. "youtube:dQw4w9WgXcQ"
    url: str


@dataclass
class Downloaded:
    path: Path
    artist: str  # artista de los metadatos de música ("" si el video no los trae)
    uploader: str
    title: str


@dataclass
class Job:
    """Una playlist a procesar: `indices` son las posiciones de `lines` que hay que bajar."""
    index: int
    name: str
    lines: list[str]
    indices: list[int] = field(default_factory=list)


# ── Listas TXT ─────────────────────────────────────────────────────────────────

def safe_name(name: str, limit: int = 150) -> str:
    """Nombre válido como archivo o carpeta en cualquier sistema."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return clean[:limit].rstrip(" .") or "untitled"


def is_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


def parse_playlist(text: str) -> list[str]:
    """Una canción por línea; ignora vacías, comentarios (#) y repetidas."""
    seen, songs = set(), []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in seen:
            seen.add(line)
            songs.append(line)
    return songs


def read_playlist(path: Path) -> list[str]:
    return parse_playlist(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def looks_like_text(path: Path) -> bool:
    """Descarta binarios que alguien arrastre por error."""
    try:
        with open(path, "rb") as fh:
            return b"\x00" not in fh.read(4096)
    except OSError:
        return False


# ── Estado de cada carpeta ─────────────────────────────────────────────────────

class FolderState:
    """Qué hay descargado en una carpeta de playlist (archivo oculto .music-dlp.json)."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.lines: dict[str, list[str]] = {}
        self.tracks: dict[str, dict] = {}
        try:
            raw = json.loads((self.folder / STATE_FILE).read_text("utf-8"))
            lines, tracks = raw.get("lines"), raw.get("tracks")
            if isinstance(lines, dict) and isinstance(tracks, dict):
                self.lines = {k: list(v) for k, v in lines.items() if isinstance(v, list)}
                self.tracks = {k: v for k, v in tracks.items() if isinstance(v, dict) and "file" in v}
        except (OSError, ValueError, AttributeError):
            pass

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (STATE_FILE + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "lines": self.lines, "tracks": self.tracks}, ensure_ascii=False), "utf-8")
        os.replace(tmp, self.folder / STATE_FILE)

    def track_file(self, key: str) -> Path | None:
        record = self.tracks.get(key)
        if not record:
            return None
        path = self.folder / record["file"]
        return path if path.is_file() else None

    def line_done(self, line: str) -> bool:
        keys = self.lines.get(line)
        return bool(keys) and all(self.track_file(k) for k in keys)

    def add(self, key: str, done: Downloaded) -> None:
        self.tracks[key] = {
            "file": os.path.relpath(done.path, self.folder),
            "artist": done.artist, "uploader": done.uploader, "title": done.title,
        }


class Library:
    """Todas las carpetas de playlist del destino, para no bajar dos veces la misma canción."""

    def __init__(self, dest: Path):
        self.dest = Path(dest)
        self.lock = threading.RLock()
        self._states: dict[Path, FolderState] = {}
        self._key_locks: dict[str, threading.Lock] = {}
        if self.dest.is_dir():
            for state_file in sorted(self.dest.glob(f"*/{STATE_FILE}")):
                self.state(state_file.parent)

    def state(self, folder: Path) -> FolderState:
        with self.lock:
            if folder not in self._states:
                self._states[folder] = FolderState(folder)
            return self._states[folder]

    def key_lock(self, key: str) -> threading.Lock:
        with self.lock:
            return self._key_locks.setdefault(key, threading.Lock())

    def find_elsewhere(self, key: str, folder: Path) -> tuple[Path, dict] | None:
        with self.lock:
            for other, state in self._states.items():
                if other != folder:
                    path = state.track_file(key)
                    if path:
                        return path, state.tracks[key]
        return None


# ── Motor ──────────────────────────────────────────────────────────────────────

class Engine:
    """Procesa los trabajos con `parallel` descargas a la vez. Avisa con emit(kind, **datos).

    Eventos: "song" (pl, i, status, detail, code) con status resolving | downloading | ok |
    copied | skipped | failed | cancelled, y "playlist" (pl, ok, skipped, failed, failed_path).
    """

    def __init__(self, backend, options: Options, emit: Callable[..., None], cancel: threading.Event | None = None):
        self.backend = backend
        self.opts = options
        self.emit = emit
        self.cancel = cancel or threading.Event()
        self.library = Library(options.dest)

    def stop(self) -> None:
        self.cancel.set()

    def folder_for(self, job: Job) -> Path:
        return self.opts.dest / safe_name(job.name)

    def run(self, jobs: list[Job]) -> None:
        self.opts.dest.mkdir(parents=True, exist_ok=True)
        results: dict[int, dict[int, str]] = {job.index: {} for job in jobs}
        with ThreadPoolExecutor(max_workers=max(1, self.opts.parallel)) as pool:
            for job in jobs:
                for i in job.indices:
                    pool.submit(self._song, job, i, results[job.index])
        for job in jobs:
            self._finish(job, results[job.index])

    def _finish(self, job: Job, statuses: dict[int, str]) -> None:
        folder = self.folder_for(job)
        failed = [job.lines[i] for i in job.indices if statuses.get(i) == "failed"]
        failed_path = None
        if self.opts.failed_file and not self.cancel.is_set():
            for name in FAILED_NAMES:
                (folder / name).unlink(missing_ok=True)
            if failed:
                folder.mkdir(parents=True, exist_ok=True)
                failed_path = folder / self.opts.failed_name
                failed_path.write_text("\n".join(failed) + "\n", "utf-8")
        counts = list(statuses.values())
        self.emit(
            "playlist", pl=job.index, failed=len(failed), failed_path=failed_path,
            ok=sum(1 for s in counts if s in ("ok", "copied")), skipped=counts.count("skipped"),
        )

    def _song(self, job: Job, i: int, statuses: dict[int, str]) -> None:
        def report(status: str, detail: str = "", code: str = "") -> None:
            self.emit("song", pl=job.index, i=i, status=status, detail=detail, code=code)

        try:
            status, detail = self._process(job, i, report)
            code = ""
        except Cancelled:
            status, detail, code = "cancelled", "", ""
        except DownloadFailed as exc:
            status, detail, code = "failed", exc.detail, exc.code
        except Exception as exc:  # un fallo inesperado no debe frenar el resto
            status, detail, code = "failed", f"{type(exc).__name__}: {exc}", "error"
        statuses[i] = status
        report(status, detail, code)

    def _names(self, job: Job, i: int, artist: str, uploader: str, title: str) -> tuple[str, str]:
        """(subcarpeta, nombre sin extensión) de una canción dentro de la carpeta de su playlist."""
        prefix = f"{i + 1:0{max(2, len(str(len(job.lines))))}d} - " if self.opts.track_numbers else ""
        if self.opts.artist_folders:
            return safe_name(artist or uploader or self.opts.unknown_artist, 100), prefix + safe_name(title)
        return "", prefix + safe_name(f"{artist} - {title}" if artist else title)

    def _process(self, job: Job, i: int, report) -> tuple[str, str]:
        if self.cancel.is_set():
            raise Cancelled
        line = job.lines[i]
        folder = self.folder_for(job)
        state = self.library.state(folder)
        skip = self.opts.skip_existing
        if skip and state.line_done(line):
            return "skipped", ""

        report("resolving")
        tracks = self.backend.resolve(line, self.cancel)
        if not tracks:
            raise DownloadFailed("no_results")

        outcomes, title = [], ""
        for track in tracks:
            if self.cancel.is_set():
                raise Cancelled
            with self.library.key_lock(track.key):
                if skip and state.track_file(track.key):
                    outcomes.append("skipped")
                    continue
                found = self.library.find_elsewhere(track.key, folder) if skip else None
                if found and found[0].suffix.lower() != f".{self.opts.audio_format}":
                    found = None  # está en otro formato: se baja de nuevo
                if found:
                    source, record = found
                    artist, uploader = record.get("artist", ""), record.get("uploader", "")
                    title = record.get("title") or source.stem
                    sub, stem = self._names(job, i, artist, uploader, title)
                    target = folder / sub / (stem + source.suffix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    done = Downloaded(target, artist, uploader, title)
                    outcomes.append("copied")
                else:
                    report("downloading", "0")
                    done = self.backend.download(
                        track, folder, lambda a, u, t: self._names(job, i, a, u, t),
                        lambda pct: report("downloading", str(pct)), self.cancel,
                    )
                    title = done.title
                    outcomes.append("ok")
                with self.library.lock:
                    state.add(track.key, done)
                    state.save()
        with self.library.lock:
            state.lines[line] = [t.key for t in tracks]
            state.save()
        for status in ("ok", "copied", "skipped"):
            if status in outcomes:
                detail = title if len(tracks) == 1 else str(len(tracks))
                return status, detail
        return "skipped", ""


# ── ffmpeg ─────────────────────────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """Carpeta o binario de ffmpeg: el incluido en el AppImage o el del sistema."""
    forced = os.environ.get("MUSIC_DLP_FFMPEG")
    if forced:
        return forced if Path(forced).exists() else None
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "ffmpeg" / "ffmpeg"
        if bundled.is_file():
            return str(bundled)
    return shutil.which("ffmpeg")


# ── Backend de yt-dlp ──────────────────────────────────────────────────────────

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _Quiet:
    def debug(self, _msg):
        pass

    info = warning = error = debug


def clean_error(exc: Exception) -> str:
    text = _ANSI.sub("", str(exc)).strip()
    return re.sub(r"^ERROR:\s*", "", text)


class YtDlpBackend:
    def __init__(self, yt_dlp, options: Options):
        self.yt = yt_dlp
        self.opts = options

    def _base(self) -> dict:
        return {"quiet": True, "no_warnings": True, "noprogress": True, "logger": _Quiet(),
                "noplaylist": True, "retries": 5, "fragment_retries": 5, "socket_timeout": 30}

    @staticmethod
    def _key(info: dict) -> str:
        return f"{(info.get('ie_key') or info.get('extractor_key') or 'video').lower()}:{info['id']}"

    def resolve(self, line: str, cancel: threading.Event) -> list[Track]:
        params = {**self._base(), "extract_flat": "in_playlist"}
        try:
            with self.yt.YoutubeDL(params) as ydl:
                if is_url(line):
                    info = ydl.extract_info(line, download=False) or {}
                    if info.get("_type") == "playlist":
                        return [
                            Track(self._key(e), e.get("url") or e.get("webpage_url") or "")
                            for e in info.get("entries") or [] if e and e.get("id")
                        ]
                    if not info.get("id"):
                        return []
                    return [Track(self._key(info), info.get("webpage_url") or line)]
                ydl.params["playlist_items"] = "1"
                queries = [("ytsearch1:" + line, "https://www.youtube.com/watch?v=")]
                if self.opts.ytmusic:
                    music = "https://music.youtube.com/search?q=" + urllib.parse.quote(line) + "#songs"
                    queries.insert(0, (music, "https://music.youtube.com/watch?v="))
                last_error = None
                for query, prefix in queries:
                    if cancel.is_set():
                        raise Cancelled
                    try:
                        info = ydl.extract_info(query, download=False) or {}
                    except self.yt.utils.DownloadError as exc:
                        last_error = exc
                        continue
                    for entry in info.get("entries") or []:
                        if entry and entry.get("id"):
                            return [Track(f"youtube:{entry['id']}", prefix + entry["id"])]
                if last_error:
                    raise last_error
                return []
        except self.yt.utils.DownloadError as exc:
            raise DownloadFailed("ytdlp", clean_error(exc)) from exc

    def _postprocessors(self) -> list[dict]:
        o = self.opts
        steps: list[dict] = []
        if o.sponsorblock:
            steps.append({"key": "SponsorBlock", "categories": ["music_offtopic"], "when": "after_filter"})
        if o.cover:
            steps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        steps.append({"key": "FFmpegExtractAudio", "preferredcodec": o.audio_format, "preferredquality": "0"})
        if o.sponsorblock:
            steps.append({"key": "ModifyChapters", "remove_sponsor_segments": ["music_offtopic"]})
        if o.metadata:
            steps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False})
        if o.cover:
            steps.append({"key": "EmbedThumbnail"})
        return steps

    def download(self, track: Track, folder: Path, names, progress, cancel: threading.Event) -> Downloaded:
        if not self.opts.ffmpeg:
            raise DownloadFailed("no_ffmpeg")
        final: list[str] = []
        last = [-1]

        def on_progress(d: dict) -> None:
            if cancel.is_set():
                raise self.yt.utils.DownloadCancelled()
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if d.get("status") == "downloading" and total:
                pct = int(d.get("downloaded_bytes", 0) * 100 / total)
                if pct >= last[0] + 5:
                    last[0] = pct
                    progress(min(pct, 99))

        def on_post(d: dict) -> None:
            if cancel.is_set():
                raise self.yt.utils.DownloadCancelled()
            if d.get("status") == "finished" and d.get("postprocessor") == "MoveFiles":
                final.append(d["info_dict"].get("filepath") or "")

        prefer_m4a = self.opts.audio_format == "m4a"
        params = {
            **self._base(),
            "format": "bestaudio[ext=m4a]/bestaudio/best" if prefer_m4a else "bestaudio/best",
            "outtmpl": {"default": "%(mdlp_stem)s.%(ext)s"},
            "writethumbnail": self.opts.cover,
            "overwrites": not self.opts.skip_existing,
            "ffmpeg_location": self.opts.ffmpeg,
            "progress_hooks": [on_progress],
            "postprocessor_hooks": [on_post],
            "postprocessors": self._postprocessors(),
        }
        try:
            with self.yt.YoutubeDL(params) as ydl:
                info = ydl.extract_info(track.url, download=False)
                if info and info.get("_type") == "playlist":
                    info = next((e for e in info.get("entries") or [] if e), None)
                if not info:
                    raise DownloadFailed("no_results")
                artist = ((info.get("artists") or [""])[0] or "").strip()
                uploader = (info.get("uploader") or info.get("channel") or "").strip()
                title = (info.get("track") or info.get("title") or info.get("id") or "").strip()
                sub, stem = names(artist, uploader, title)
                info["mdlp_stem"] = stem
                target = folder / sub
                target.mkdir(parents=True, exist_ok=True)
                ydl.params["paths"] = {"home": str(target)}
                if cancel.is_set():
                    raise Cancelled
                ydl.process_ie_result(info, download=True)
        except self.yt.utils.DownloadCancelled as exc:
            raise Cancelled from exc
        except self.yt.utils.DownloadError as exc:
            raise DownloadFailed("ytdlp", clean_error(exc)) from exc
        if not final or not final[-1] or not Path(final[-1]).is_file():
            raise DownloadFailed("ytdlp", "yt-dlp no dejó ningún archivo")
        return Downloaded(Path(final[-1]), artist, uploader, title)
