# SPDX-License-Identifier: GPL-3.0-or-later
"""Genera las capturas del README con datos inventados.

Uso: QT_QPA_PLATFORM=offscreen PYTHONPATH=src python tools/screenshots.py <carpeta de salida>
"""
import json
import os
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="music-dlp-shots-"))
CONFIG = tmp / "home" / ".config" / "music-dlp"
os.environ["MUSIC_DLP_CONFIG"] = str(CONFIG)
os.environ["MUSIC_DLP_DATA"] = str(tmp / "home" / ".local" / "share" / "music-dlp")
os.environ["HOME"] = str(tmp / "home")
CONFIG.mkdir(parents=True)
(tmp / "home" / "Music").mkdir(parents=True)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from music_dlp import i18n  # noqa: E402
from music_dlp.ui import TAB_PLAYLISTS, TAB_SETTINGS, TAB_SPOTIFY, MainWindow  # noqa: E402

LISTS = {
    "Rock nacional": [
        ("De música ligera - Soda Stereo", "ok", "De Música Ligera (Remasterizado 2007)"),
        ("Persiana americana - Soda Stereo", "ok", "Persiana Americana"),
        ("Flaca - Andrés Calamaro", "ok", "Flaca"),
        ("Seminare - Serú Girán", "skipped", ""),
        ("Rasguña las piedras - Sui Generis", "downloading", "65"),
        ("Muchacha (ojos de papel) - Almendra", "downloading", "20"),
        ("Jijiji - Patricio Rey y sus Redonditos de Ricota", "resolving", ""),
        ("El amor después del amor - Fito Páez", "resolving", ""),
        ("Mariposa tecknicolor - Fito Páez", "queued", ""),
        ("Lamento boliviano - Los Enanitos Verdes", "queued", ""),
    ],
    "Clásicos de los 80": [
        ("Take On Me - a-ha", "ok", "Take On Me"),
        ("Africa - TOTO", "copied", "Africa"),
        ("Canción inventada que no existe - Nadie", "failed", ""),
        ("https://www.youtube.com/watch?v=xxxxxxxxxxx", "failed", "[youtube] xxxxxxxxxxx: Video unavailable"),
        ("Everybody Wants to Rule the World - Tears for Fears", "ok", "Everybody Wants To Rule The World"),
    ],
    "Para estudiar": [("Clair de Lune - Claude Debussy", "pending", ""), ("Gymnopédie No. 1 - Erik Satie", "pending", ""),
                      ("Nuvole Bianche - Ludovico Einaudi", "pending", "")],
}
EXPORTS = [("Rock nacional", 48), ("Clásicos de los 80", 112), ("Para estudiar", 37), ("Viaje en ruta", 64),
           ("Entrenar", 29), ("Domingo a la mañana", 53), ("Canciones que te gustan", 486)]

app = QApplication(sys.argv)
app.setStyle("Fusion")


def shot(dark: bool, lang: str) -> None:
    os.environ["MUSIC_DLP_THEME"] = "dark" if dark else "light"
    (CONFIG / "config.json").write_text(json.dumps({"language": lang, "cred_mode": "memory", "dest": str(tmp / "home" / "Music")}))
    lists = tmp / f"lists-{lang}"
    lists.mkdir(exist_ok=True)
    for name, songs in LISTS.items():
        (lists / f"{name}.txt").write_text("\n".join(s[0] for s in songs) + "\n", "utf-8")
    window = MainWindow()
    window.resize(1080, 780)
    window.show()
    while window.running("probe"):
        app.processEvents()
    tag = f"{'dark' if dark else 'light'}-{lang}"
    window.grab().save(str(out / f"empty-{tag}.png"))

    window.add_paths([str(lists / f"{name}.txt") for name in LISTS])
    window._run = {"total": 18, "done": 9, "bad": 2, "ok": 6, "skipped": 1}
    for pl, songs in enumerate(LISTS.values()):
        for i, (_line, status, detail) in enumerate(songs):
            song = window.playlists[pl].songs[i]
            song.status, song.detail = status, detail
            song.code = "no_results" if status == "failed" and not detail else ("ytdlp" if status == "failed" else "")
        window.refresh_playlist(pl, songs=True)
    window.tree.topLevelItem(0).setExpanded(True)
    window.tree.topLevelItem(1).setExpanded(True)
    window.log(i18n.tr("log_dl_start", songs=i18n.songs(18), dest="~/Music", p=4, fmt="MP3"), "accent")
    window.log(i18n.tr("log_song_ok", pl="Rock nacional", line="De música ligera - Soda Stereo", title="De Música Ligera (Remasterizado 2007)"), "ok")
    window.log(i18n.tr("log_song_skipped", pl="Rock nacional", line="Seminare - Serú Girán"), "muted")
    window.log(i18n.tr("log_song_copied", pl="Clásicos de los 80", line="Africa - TOTO"), "ok")
    window.log(i18n.tr("log_song_failed", pl="Clásicos de los 80", line="Canción inventada que no existe - Nadie", error=i18n.tr("err_no_results")), "err")
    window.log(i18n.tr("log_song_ok", pl="Rock nacional", line="Flaca - Andrés Calamaro", title="Flaca"), "ok")
    window.progress.setRange(0, 18)
    window.progress.setValue(9)
    window.progress.show()
    window.set_status("status_downloading_bad", {"done": 9, "n": 18, "bad": 2})
    window.btn_download.setText(" " + i18n.tr("stop"))
    window.btn_download.setIcon(window.icon("stop", "accent_text", 20))
    app.processEvents()
    window.grab().save(str(out / f"playlists-{tag}.png"))
    window.update_buttons()

    window.progress.hide()
    window.set_status("status_ready")
    window.edit_id.setText("3f1c9a7e5b2d4c8fa6e0d1b2c3a4f5e6")
    window.edit_secret.setText("x" * 32)
    liked = i18n.tr("liked_name")
    window._show_exports([(liked if n == "Canciones que te gustan" else n, tmp / f"{n}.txt", c) for n, c in EXPORTS])
    window.sp_tree.topLevelItem(4).setCheckState(0, Qt.CheckState.Unchecked)
    window.log(i18n.tr("log_sp_found", n=7, dest="~/.local/share/music-dlp/playlists"), "accent")
    for n, c in EXPORTS[:3]:
        window.log(i18n.tr("log_sp_ok", name=n, songs=i18n.songs(c), file=f"{n}.txt"), "ok")
    window.log(i18n.tr("log_sp_done", n=len(EXPORTS)), "ok")
    window.tabs.setCurrentIndex(TAB_SPOTIFY)
    app.processEvents()
    window.grab().save(str(out / f"spotify-{tag}.png"))

    window.tabs.setCurrentIndex(TAB_SETTINGS)
    app.processEvents()
    window.grab().save(str(out / f"settings-{tag}.png"))
    window.tabs.setCurrentIndex(TAB_PLAYLISTS)
    window.close()
    window.deleteLater()
    app.processEvents()


for dark in (False, True):
    for lang in ("es", "en"):
        shot(dark, lang)
print(sorted(p.name for p in out.glob("*.png")))
