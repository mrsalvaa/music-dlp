# SPDX-License-Identifier: GPL-3.0-or-later
"""Carpetas de la app y ajustes guardados en ~/.config/music-dlp/config.json."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP = "music-dlp"
FORMATS = ("mp3", "opus", "m4a", "flac")
CRED_MODES = ("keyring", "file", "memory")


def config_dir() -> Path:
    """Carpeta de configuración (MUSIC_DLP_CONFIG la cambia, para pruebas)."""
    forced = os.environ.get("MUSIC_DLP_CONFIG")
    if forced:
        return Path(forced)
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP


def data_dir() -> Path:
    """Carpeta de datos (MUSIC_DLP_DATA la cambia, para pruebas)."""
    forced = os.environ.get("MUSIC_DLP_DATA")
    if forced:
        return Path(forced)
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP


def music_dir() -> Path:
    """Carpeta de música del usuario según XDG (~/Música, ~/Music…)."""
    home = Path.home()
    try:
        text = (Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "user-dirs.dirs").read_text("utf-8")
        found = re.search(r'^XDG_MUSIC_DIR="(.+)"\s*$', text, re.M)
        if found:
            path = Path(found.group(1).replace("$HOME", str(home)))
            if path.is_absolute() and path != home:
                return path
    except OSError:
        pass
    return home / "Music"


@dataclass
class Settings:
    dest: str = ""  # vacío = carpeta de música del sistema
    txt_dir: str = ""  # vacío = <datos>/playlists
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
    cred_mode: str = "keyring"
    language: str = ""  # vacío = idioma del sistema
    own_only: bool = False
    include_liked: bool = True

    def dest_path(self) -> Path:
        return Path(self.dest).expanduser() if self.dest else music_dir()

    def txt_path(self) -> Path:
        return Path(self.txt_dir).expanduser() if self.txt_dir else data_dir() / "playlists"

    def normalize(self) -> None:
        """Deja valores válidos aunque el archivo se haya editado a mano."""
        defaults = Settings()
        for f in fields(self):
            if not isinstance(getattr(self, f.name), type(getattr(defaults, f.name))):
                setattr(self, f.name, getattr(defaults, f.name))
        self.parallel = min(16, max(1, self.parallel))
        if self.audio_format not in FORMATS:
            self.audio_format = "mp3"
        if self.cred_mode not in CRED_MODES:
            self.cred_mode = "keyring"


def load() -> Settings:
    settings = Settings()
    try:
        raw = json.loads((config_dir() / "config.json").read_text("utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(raw, dict):
        for f in fields(settings):
            if f.name in raw:
                setattr(settings, f.name, raw[f.name])
    settings.normalize()
    return settings


def save(settings: Settings) -> None:
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "config.json.tmp"
    tmp.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n", "utf-8")
    os.replace(tmp, folder / "config.json")
