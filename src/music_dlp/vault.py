# SPDX-License-Identifier: GPL-3.0-or-later
"""Dónde se guardan las credenciales y la sesión de Spotify.

Tres modos: "keyring" (llavero del sistema por Secret Service: KWallet, GNOME Keyring…),
"file" (archivo con permisos 600) y "memory" (nada toca el disco).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SERVICE = "music-dlp"
ACCOUNT = "spotify"
FILE_NAME = "credentials.json"


class VaultError(Exception):
    """El almacén elegido no está disponible o falló."""


def _system_keyring():
    try:
        from keyring.backends import SecretService

        backend = SecretService.Keyring()
        SecretService.Keyring.priority  # lanza si no hay Secret Service
        return backend
    except Exception as exc:  # sin D-Bus, sin llavero, etc.
        raise VaultError(str(exc)) from exc


class Vault:
    """Guarda un único diccionario: client_id, client_secret y token."""

    def __init__(self, mode: str, folder: Path, keyring_backend=None):
        self.mode = mode
        self.path = Path(folder) / FILE_NAME
        self._keyring = keyring_backend
        self._memory: dict = {}

    def _backend(self):
        if self._keyring is None:
            self._keyring = _system_keyring()
        return self._keyring

    def load(self) -> dict:
        if self.mode == "memory":
            return dict(self._memory)
        try:
            if self.mode == "file":
                raw = self.path.read_text("utf-8")
            else:
                raw = self._backend().get_password(SERVICE, ACCOUNT)
        except FileNotFoundError:
            return {}
        except VaultError:
            raise
        except Exception as exc:
            raise VaultError(str(exc)) from exc
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict) -> None:
        if self.mode == "memory":
            self._memory = dict(data)
            return
        raw = json.dumps(data)
        try:
            if self.mode == "file":
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(raw)
                os.chmod(self.path, 0o600)
            else:
                self._backend().set_password(SERVICE, ACCOUNT, raw)
        except VaultError:
            raise
        except Exception as exc:
            raise VaultError(str(exc)) from exc

    def clear(self) -> None:
        """Borra lo guardado en este modo."""
        self._memory = {}
        if self.mode == "file":
            self.path.unlink(missing_ok=True)
        elif self.mode == "keyring":
            try:
                self._backend().delete_password(SERVICE, ACCOUNT)
            except VaultError:
                raise
            except Exception:
                pass  # no había nada guardado


def wipe_all(folder: Path, keyring_backend=None) -> None:
    """Borra las credenciales de todos los almacenes persistentes."""
    Vault("file", folder).clear()
    try:
        Vault("keyring", folder, keyring_backend).clear()
    except VaultError:
        pass
