# SPDX-License-Identifier: GPL-3.0-or-later
"""Punto de entrada: `python -m music_dlp [listas .txt…]`."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from . import __version__, theme
from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("music-dlp")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("music-dlp")
    app.setStyle("Fusion")
    app.setWindowIcon(theme.app_icon())
    window = MainWindow()
    window.show()
    paths = [a for a in app.arguments()[1:] if not a.startswith("-")]
    if paths:
        window.add_paths(paths)
        if os.environ.get("MUSIC_DLP_AUTORUN"):  # para pruebas: descarga, imprime la consola y sale
            window.autorun()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
