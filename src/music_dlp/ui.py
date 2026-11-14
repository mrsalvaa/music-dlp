# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana principal de music-dlp: pestañas Playlists, Spotify y Ajustes, y la consola."""

from __future__ import annotations

import html
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__, core, i18n, spotify, theme, updater, vault
from . import settings as settings_mod
from .i18n import tr

COL_NAME, COL_RESULT, COL_STATUS = range(3)
FINAL = ("ok", "copied", "skipped", "failed", "cancelled")
DONE = ("ok", "copied", "skipped")
TAB_PLAYLISTS, TAB_SPOTIFY, TAB_SETTINGS = range(3)


def pretty(path: Path) -> str:
    try:
        return "~/" + str(Path(path).relative_to(Path.home()))
    except ValueError:
        return str(path)


def shorten(text: str, limit: int = 34) -> str:
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


@dataclass
class Song:
    line: str
    status: str = "pending"  # pending | queued | resolving | downloading | ok | copied | skipped | failed | cancelled
    detail: str = ""
    code: str = ""


@dataclass
class Playlist:
    path: Path
    name: str
    songs: list[Song] = field(default_factory=list)

    def count(self, *statuses: str) -> int:
        return sum(1 for s in self.songs if s.status in statuses)


# ── Trabajo en segundo plano ───────────────────────────────────────────────────

class Worker(QObject):
    """Corre fn(emit, cancel) en un hilo; los avisos llegan a la ventana como señales."""

    event = Signal(str, str, object)
    finished = Signal(str, object, object)

    def __init__(self, name: str, fn):
        super().__init__()
        self.name = name
        self.cancel = threading.Event()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        result = error = None
        try:
            result = self._fn(lambda kind, **data: self.event.emit(self.name, kind, data), self.cancel)
        except Exception as exc:  # se informa en la consola
            error = exc
        self.finished.emit(self.name, result, error)


def make_card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(10)
    return frame, lay


# ── Ventana principal ──────────────────────────────────────────────────────────

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("music-dlp")
        self.setWindowIcon(theme.app_icon())
        self.resize(1080, 780)
        self.setMinimumSize(900, 640)
        self.setAcceptDrops(True)

        self.settings = settings_mod.load()
        i18n.set_language(self.settings.language or i18n.system_language())
        self.colors = theme.palette(False)
        self.playlists: list[Playlist] = []
        self.exports: list[tuple[str, Path, int]] = []
        self.creds: dict = {}
        self.vault = vault.Vault(self.settings.cred_mode, settings_mod.config_dir())
        self._tasks: dict[str, tuple[QThread, Worker]] = {}
        self._handlers: dict[str, tuple] = {}
        self._texts: list[tuple] = []  # (función que pone el texto, clave, prefijo)
        self._tips: list[tuple] = []
        self._icons: list[tuple] = []  # (botón, ícono, clave de color)
        self._icon_cache: dict = {}
        self._status: tuple[str, dict] = ("status_ready", {})
        self._run = {"total": 0, "done": 0, "bad": 0, "ok": 0, "skipped": 0}
        self._yt_info: tuple[str, str] | None = None
        self._autorun = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(10)

        # Cabecera
        head = QHBoxLayout()
        head.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(theme.app_icon().pixmap(QSize(30, 30)))
        head.addWidget(logo)
        title = QLabel("music-dlp")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_lang = QPushButton()
        self.btn_lang.setObjectName("flat")
        self.btn_lang.clicked.connect(self.toggle_language)
        head.addWidget(self.btn_lang)
        root.addLayout(head)

        # Pestañas arriba, consola abajo
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_playlists(), "")
        self.tabs.addTab(self._build_spotify(), "")
        self.tabs.addTab(self._build_settings(), "")
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self._build_console())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 170])
        root.addWidget(splitter, 1)

        QShortcut(QKeySequence.StandardKey.Open, self, self.pick_files)
        QShortcut(QKeySequence("Ctrl+D"), self, self.toggle_download)
        QShortcut(QKeySequence.StandardKey.Delete, self.tree, self.remove_selected)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self.apply_theme())
        self.apply_theme()

        self.log(tr("log_welcome", version=__version__), "accent")
        self.log(tr("log_dest", dest=pretty(self.settings.dest_path())), "muted")
        self._load_credentials()
        self._load_existing_exports()
        self.start_task("probe", self._probe, None, self._probe_done)

    # ── Construcción ──

    def _text(self, setter, key: str, prefix: str = "") -> None:
        self._texts.append((setter, key, prefix))

    def _button(self, key: str, icon: str | None = None, tip: str | None = None, primary: bool = False,
                flat: bool = False) -> QPushButton:
        button = QPushButton()
        if primary:
            button.setObjectName("primary")
        elif flat:
            button.setObjectName("flat")
        if key:
            self._text(button.setText, key, " " if icon else "")
        if icon:
            self._icons.append((button, icon, "accent_text" if primary else "text"))
        if tip:
            self._tips.append((button, tip))
        return button

    def _build_playlists(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_add = self._button("add", "add", "add_tip")
        self.btn_remove = self._button("remove", "remove", "remove_tip")
        self.btn_clear = self._button("clear", "clear", "clear_tip")
        self.btn_add.clicked.connect(self.pick_files)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_list)
        for b in (self.btn_add, self.btn_remove, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        self.lbl_parallel = QLabel()
        self.lbl_parallel.setObjectName("muted")
        self._text(self.lbl_parallel.setText, "parallel")
        bar.addWidget(self.lbl_parallel)
        self.spin_parallel = QSpinBox()
        self.spin_parallel.setRange(1, 16)
        self.spin_parallel.setValue(self.settings.parallel)
        self.spin_parallel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_parallel.setFixedWidth(78)
        self.spin_parallel.valueChanged.connect(lambda v: self._set("parallel", v))
        self._tips.append((self.spin_parallel, "parallel_tip"))
        self.lbl_parallel.setBuddy(self.spin_parallel)
        bar.addWidget(self.spin_parallel)
        self.btn_dest = self._button("", "folder")
        self.btn_dest.clicked.connect(self.pick_destination)
        bar.addWidget(self.btn_dest)
        self.btn_open = self._button("open_folder")
        self.btn_open.clicked.connect(self.open_destination)
        bar.addWidget(self.btn_open)
        self.btn_download = QPushButton()
        self.btn_download.setObjectName("primary")
        self.btn_download.clicked.connect(self.toggle_download)
        bar.addWidget(self.btn_download)
        lay.addLayout(bar)

        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(1, 1, 1, 1)
        self.stack = QStackedWidget()
        card_lay.addWidget(self.stack)

        empty = QWidget()
        empty_lay = QVBoxLayout(empty)
        empty_lay.setContentsMargins(22, 22, 22, 22)
        self.drop = QFrame()
        self.drop.setObjectName("drop")
        drop_lay = QVBoxLayout(self.drop)
        drop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_lay.setSpacing(8)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel()
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text(empty_title.setText, "empty_title")
        empty_sub = QLabel()
        empty_sub.setObjectName("emptySub")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub.setWordWrap(True)
        self._text(empty_sub.setText, "empty_sub")
        for w in (self.empty_icon, empty_title, empty_sub):
            drop_lay.addWidget(w)
        empty_lay.addWidget(self.drop)
        self.stack.addWidget(empty)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setIndentation(22)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_RESULT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_STATUS, 230)
        header.setSectionsMovable(False)
        self.tree.itemSelectionChanged.connect(self.update_buttons)
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.stack.addWidget(self.tree)
        lay.addWidget(card, 1)
        return page

    def _build_spotify(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(12)

        # Formulario
        form, f = make_card()
        title = QLabel()
        title.setObjectName("section")
        self._text(title.setText, "sp_title")
        f.addWidget(title)
        intro = QLabel()
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        intro.setObjectName("muted")
        intro.setMinimumHeight(40)
        self._text(intro.setText, "sp_intro")
        f.addWidget(intro)
        uri_row = QHBoxLayout()
        uri = QLabel(spotify.REDIRECT_URI)
        uri.setObjectName("mono")
        uri.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        uri_row.addWidget(uri, 1)
        self.btn_copy_uri = self._button("", "copy", "sp_copy_uri")
        self.btn_copy_uri.clicked.connect(self._copy_uri)
        uri_row.addWidget(self.btn_copy_uri)
        f.addLayout(uri_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        lbl_id = QLabel()
        self._text(lbl_id.setText, "sp_client_id")
        self.edit_id = QLineEdit()
        self.edit_id.setAccessibleName("Client ID")
        lbl_id.setBuddy(self.edit_id)
        grid.addWidget(lbl_id, 0, 0)
        grid.addWidget(self.edit_id, 0, 1, 1, 2)
        lbl_secret = QLabel()
        self._text(lbl_secret.setText, "sp_client_secret")
        self.edit_secret = QLineEdit()
        self.edit_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_secret.setAccessibleName("Client Secret")
        lbl_secret.setBuddy(self.edit_secret)
        self.btn_show = QPushButton()
        self.btn_show.setCheckable(True)
        self.btn_show.toggled.connect(self._toggle_secret)
        grid.addWidget(lbl_secret, 1, 0)
        grid.addWidget(self.edit_secret, 1, 1)
        grid.addWidget(self.btn_show, 1, 2)
        grid.setColumnStretch(1, 1)
        f.addLayout(grid)
        self.lbl_store = QLabel()
        self.lbl_store.setObjectName("hint")
        self.lbl_store.setWordWrap(True)
        self.lbl_store.setMinimumHeight(34)
        f.addWidget(self.lbl_store)
        f.addSpacing(4)

        self.chk_own = QCheckBox()
        self.chk_own.setChecked(self.settings.own_only)
        self.chk_own.toggled.connect(lambda v: self._set("own_only", v))
        self._text(self.chk_own.setText, "sp_own_only")
        f.addWidget(self.chk_own)
        self.chk_liked = QCheckBox()
        self.chk_liked.setChecked(self.settings.include_liked)
        self.chk_liked.toggled.connect(lambda v: self._set("include_liked", v))
        self._text(self.chk_liked.setText, "sp_liked")
        f.addWidget(self.chk_liked)
        f.addStretch(1)
        actions = QHBoxLayout()
        self.btn_sp_cancel = self._button("sp_cancel")
        self.btn_sp_cancel.clicked.connect(lambda: self.cancel_task("spotify"))
        self.btn_export = self._button("sp_export", "cloud", "sp_export_tip", primary=True)
        self.btn_export.clicked.connect(self.export_spotify)
        self.edit_id.returnPressed.connect(self.export_spotify)
        self.edit_secret.returnPressed.connect(self.export_spotify)
        actions.addStretch(1)
        actions.addWidget(self.btn_sp_cancel)
        actions.addWidget(self.btn_export)
        f.addLayout(actions)
        lay.addWidget(form, 5)

        # Resultados
        results, r = make_card()
        r_title = QLabel()
        r_title.setObjectName("section")
        self._text(r_title.setText, "sp_results")
        r.addWidget(r_title)
        self.sp_stack = QStackedWidget()
        placeholder = QLabel()
        placeholder.setObjectName("muted")
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text(placeholder.setText, "sp_results_empty")
        self.sp_stack.addWidget(placeholder)
        self.sp_tree = QTreeWidget()
        self.sp_tree.setColumnCount(2)
        self.sp_tree.setRootIsDecorated(False)
        self.sp_tree.setUniformRowHeights(True)
        self.sp_tree.setFrameShape(QFrame.Shape.NoFrame)
        sp_header = self.sp_tree.header()
        sp_header.setStretchLastSection(False)
        sp_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sp_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sp_tree.itemChanged.connect(lambda *_a: self.update_buttons())
        self.sp_stack.addWidget(self.sp_tree)
        r.addWidget(self.sp_stack, 1)
        r_actions = QHBoxLayout()
        self.btn_sp_all = self._button("sp_all", flat=True)
        self.btn_sp_none = self._button("sp_none", flat=True)
        self.btn_sp_all.clicked.connect(lambda: self._check_exports(True))
        self.btn_sp_none.clicked.connect(lambda: self._check_exports(False))
        self.btn_sp_open = self._button("sp_open_txt", "folder")
        self.btn_sp_open.clicked.connect(lambda: self._open_path(self.settings.txt_path()))
        self.btn_import = QPushButton()
        self.btn_import.setObjectName("primary")
        self._icons.append((self.btn_import, "import", "accent_text"))
        self._tips.append((self.btn_import, "sp_import_tip"))
        self.btn_import.clicked.connect(self.import_exports)
        r_actions.addWidget(self.btn_sp_all)
        r_actions.addWidget(self.btn_sp_none)
        r_actions.addStretch(1)
        r_actions.addWidget(self.btn_sp_open)
        r_actions.addWidget(self.btn_import)
        r.addLayout(r_actions)
        lay.addWidget(results, 6)
        return page

    def _option(self, lay: QVBoxLayout, name: str, key: str, tip: str | None = None) -> QCheckBox:
        box = QCheckBox()
        box.setChecked(getattr(self.settings, name))
        box.toggled.connect(lambda v, n=name: self._set(n, v))
        self._text(box.setText, key)
        if tip:
            self._tips.append((box, tip))
        lay.addWidget(box)
        return box

    def _build_settings(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 4, 4, 4)
        lay.setSpacing(12)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(12)
        right.setSpacing(12)
        lay.addLayout(left, 1)
        lay.addLayout(right, 1)

        # Descargas
        card, c = make_card()
        section = QLabel()
        section.setObjectName("section")
        self._text(section.setText, "set_downloads")
        c.addWidget(section)
        fmt_row = QHBoxLayout()
        fmt_label = QLabel()
        self._text(fmt_label.setText, "set_format")
        fmt_row.addWidget(fmt_label)
        self.combo_format = QComboBox()
        for fmt in settings_mod.FORMATS:
            self.combo_format.addItem("", fmt)
        self.combo_format.setCurrentIndex(settings_mod.FORMATS.index(self.settings.audio_format))
        self.combo_format.currentIndexChanged.connect(lambda i: self._set("audio_format", settings_mod.FORMATS[i]))
        fmt_label.setBuddy(self.combo_format)
        fmt_row.addWidget(self.combo_format, 1)
        c.addLayout(fmt_row)
        self._option(c, "metadata", "opt_metadata")
        self._option(c, "cover", "opt_cover")
        self._option(c, "skip_existing", "opt_skip", "opt_skip_tip")
        self._option(c, "failed_file", "opt_failed", "opt_failed_tip")
        self._option(c, "ytmusic", "opt_ytmusic", "opt_ytmusic_tip")
        self._option(c, "artist_folders", "opt_artist", "opt_artist_tip")
        self._option(c, "track_numbers", "opt_numbers", "opt_numbers_tip")
        self._option(c, "sponsorblock", "opt_sponsor", "opt_sponsor_tip")
        c.addSpacing(4)
        txt_label = QLabel()
        self._text(txt_label.setText, "set_txt_dir")
        c.addWidget(txt_label)
        self.btn_txt_dir = self._button("", "folder")
        self.btn_txt_dir.clicked.connect(self.pick_txt_dir)
        c.addWidget(self.btn_txt_dir)
        left.addWidget(card)
        left.addStretch(1)

        # Seguridad
        card, c = make_card()
        section = QLabel()
        section.setObjectName("section")
        self._text(section.setText, "set_security")
        c.addWidget(section)
        intro = QLabel()
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        self._text(intro.setText, "sec_intro")
        c.addWidget(intro)
        self.mode_group = QButtonGroup(self)
        self.mode_radios: dict[str, QRadioButton] = {}
        self.mode_subs: dict[str, QLabel] = {}
        for index, mode in enumerate(settings_mod.CRED_MODES):
            radio = QRadioButton()
            self._text(radio.setText, f"sec_{mode}")
            radio.setChecked(mode == self.settings.cred_mode)
            self.mode_group.addButton(radio, index)
            self.mode_radios[mode] = radio
            c.addWidget(radio)
            sub = QLabel()
            sub.setObjectName("hint")
            sub.setWordWrap(True)
            sub.setContentsMargins(26, 0, 0, 4)
            self.mode_subs[mode] = sub
            c.addWidget(sub)
        self.mode_group.idToggled.connect(self._mode_toggled)
        self.btn_forget = self._button("sec_forget", "clear", "sec_forget_tip")
        self.btn_forget.clicked.connect(self.forget_credentials)
        row = QHBoxLayout()
        row.addWidget(self.btn_forget)
        row.addStretch(1)
        c.addLayout(row)
        right.addWidget(card)

        # yt-dlp
        card, c = make_card()
        section = QLabel()
        section.setObjectName("section")
        self._text(section.setText, "set_ytdlp")
        c.addWidget(section)
        self.lbl_yt = QLabel()
        c.addWidget(self.lbl_yt)
        note = QLabel()
        note.setObjectName("hint")
        note.setWordWrap(True)
        self._text(note.setText, "yt_note")
        c.addWidget(note)
        self.btn_update = self._button("yt_update", "refresh")
        self.btn_update.clicked.connect(self.update_ytdlp)
        row = QHBoxLayout()
        row.addWidget(self.btn_update)
        row.addStretch(1)
        c.addLayout(row)
        right.addWidget(card)

        # Acerca de
        card, c = make_card()
        section = QLabel()
        section.setObjectName("section")
        self._text(section.setText, "set_about")
        c.addWidget(section)
        self.lbl_about = QLabel()
        self.lbl_about.setObjectName("muted")
        self.lbl_about.setWordWrap(True)
        self.lbl_about.setOpenExternalLinks(True)
        c.addWidget(self.lbl_about)
        right.addWidget(card)
        right.addStretch(1)
        return scroll

    def _build_console(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        lay.addWidget(self.progress)
        head = QHBoxLayout()
        head.setSpacing(8)
        label = QLabel()
        label.setObjectName("section")
        self._text(label.setText, "console")
        head.addWidget(label)
        self.status = QLabel()
        self.status.setObjectName("status")
        head.addWidget(self.status)
        head.addStretch(1)
        self.btn_console_copy = self._button("console_copy", "copy", flat=True)
        self.btn_console_clear = self._button("console_clear", "clear", flat=True)
        head.addWidget(self.btn_console_copy)
        head.addWidget(self.btn_console_clear)
        lay.addLayout(head)
        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 8, 6, 8)
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setFrameShape(QFrame.Shape.NoFrame)
        self.console.setMinimumHeight(70)
        card_lay.addWidget(self.console)
        lay.addWidget(card, 1)
        self.btn_console_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.console.toPlainText()))
        self.btn_console_clear.clicked.connect(self.console.clear)
        return box

    # ── Tema, idioma y textos ──

    def icon(self, name: str, color_key: str, size: int = 18):
        key = (name, color_key, size)
        if key not in self._icon_cache:
            self._icon_cache[key] = theme.icon(name, self.colors[color_key], size, disabled=self.colors["muted"])
        return self._icon_cache[key]

    def apply_theme(self) -> None:
        forced = os.environ.get("MUSIC_DLP_THEME", "")
        if forced in ("dark", "light"):
            dark = forced == "dark"
        else:
            dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        self.colors = theme.palette(dark)
        self._icon_cache.clear()
        QApplication.instance().setPalette(theme.qpalette(self.colors))
        self.setStyleSheet(theme.stylesheet(self.colors))
        for button, name, color_key in self._icons:
            button.setIcon(self.icon(name, color_key, 20))
        self.empty_icon.setPixmap(theme.icon("music", self.colors["muted"], 44).pixmap(QSize(44, 44)))
        self.retranslate()

    def toggle_language(self) -> None:
        i18n.set_language("en" if i18n.language() == "es" else "es")
        self._set("language", i18n.language())
        self.retranslate()

    def retranslate(self) -> None:
        for setter, key, prefix in self._texts:
            setter(prefix + tr(key))
        for widget, key in self._tips:
            widget.setToolTip(tr(key))
        for index, key in enumerate(("tab_playlists", "tab_spotify", "tab_settings")):
            self.tabs.setTabText(index, tr(key))
        self.btn_lang.setIcon(theme.flag(i18n.language()))
        self.btn_lang.setIconSize(QSize(27, 18))
        self.btn_lang.setToolTip(tr("lang_tip"))
        self.btn_lang.setAccessibleName(tr("lang_tip"))
        self.btn_copy_uri.setAccessibleName(tr("sp_copy_uri"))
        self.btn_show.setText(tr("hide") if self.btn_show.isChecked() else tr("show"))
        self.tree.setHeaderLabels([tr("col_name"), tr("col_result"), tr("col_status")])
        self.sp_tree.setHeaderLabels([tr("sp_col_name"), tr("sp_col_songs")])
        for index, fmt in enumerate(settings_mod.FORMATS):
            self.combo_format.setItemText(index, tr(f"fmt_{fmt}"))
        self.mode_subs["keyring"].setText(tr("sec_keyring_sub"))
        self.mode_subs["file"].setText(tr("sec_file_sub", path=pretty(settings_mod.config_dir() / vault.FILE_NAME)))
        self.mode_subs["memory"].setText(tr("sec_memory_sub"))
        self.lbl_about.setText(tr("about_text", version=__version__))
        self._refresh_paths()
        self._refresh_store_label()
        self._refresh_yt_label()
        for index in range(len(self.playlists)):
            self.refresh_playlist(index, songs=True)
        self.set_status(*self._status)
        self.update_buttons()

    def _refresh_paths(self) -> None:
        dest = pretty(self.settings.dest_path())
        self.btn_dest.setText(" " + shorten(dest))
        self.btn_dest.setToolTip(tr("dest_tip", dest=dest))
        self.btn_dest.setAccessibleName(tr("dest_pick"))
        self.btn_open.setToolTip(tr("open_folder_tip", dest=dest))
        self.btn_txt_dir.setText(" " + shorten(pretty(self.settings.txt_path()), 48))
        self.btn_txt_dir.setToolTip(tr("txt_pick"))

    def _refresh_store_label(self) -> None:
        self.lbl_store.setText(tr(f"sp_store_{self.vault.mode}") + " " + tr("sp_store_change"))

    def _refresh_yt_label(self) -> None:
        if self._yt_info:
            version, origin = self._yt_info
            self.lbl_yt.setText(tr("yt_version", version=version, origin=tr(f"origin_{origin}")))
        else:
            self.lbl_yt.setText(tr("yt_loading"))

    def set_status(self, key: str, args: dict | None = None) -> None:
        self._status = (key, args or {})
        self.status.setText("· " + tr(key, **(args or {})))

    def log(self, text: str, kind: str = "info") -> None:
        color = {"ok": "ok", "err": "err", "muted": "muted", "accent": "accent", "warn": "warn"}.get(kind, "text")
        stamp = time.strftime("%H:%M:%S")
        self.console.appendHtml(
            f"<span style='color:{self.colors['muted']}'>{stamp}</span>&nbsp;&nbsp;"
            f"<span style='color:{self.colors[color]}; white-space:pre-wrap'>{html.escape(text)}</span>"
        )
        bar = self.console.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set(self, name: str, value) -> None:
        setattr(self.settings, name, value)
        try:
            settings_mod.save(self.settings)
        except OSError:
            pass

    # ── Tareas ──

    def start_task(self, name: str, fn, on_event, on_done) -> None:
        thread = QThread(self)
        worker = Worker(name, fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.event.connect(self._task_event)
        worker.finished.connect(self._task_finished)
        self._tasks[name] = (thread, worker)
        self._handlers[name] = (on_event, on_done)
        thread.start()
        self.update_buttons()

    def running(self, name: str) -> bool:
        return name in self._tasks

    def cancel_task(self, name: str) -> None:
        if name in self._tasks:
            self._tasks[name][1].cancel.set()

    @Slot(str, str, object)
    def _task_event(self, name: str, kind: str, data: dict) -> None:
        handler = self._handlers.get(name, (None, None))[0]
        if handler:
            handler(kind, data)

    @Slot(str, object, object)
    def _task_finished(self, name: str, result, error) -> None:
        thread, _worker = self._tasks.pop(name)
        thread.quit()
        thread.wait()
        thread.deleteLater()
        on_done = self._handlers.pop(name)[1]
        if on_done:
            on_done(result, error)
        self.update_buttons()

    # ── Botones ──

    def update_buttons(self) -> None:
        downloading = self.running("download")
        exporting = self.running("spotify")
        has = bool(self.playlists)
        self.stack.setCurrentIndex(1 if has else 0)
        selected = any(i.parent() is None for i in self.tree.selectedItems())
        self.btn_remove.setEnabled(not downloading and selected)
        self.btn_clear.setEnabled(not downloading and has)
        self.btn_dest.setEnabled(not downloading)
        self.spin_parallel.setEnabled(not downloading)
        pending = any(s.status not in DONE for p in self.playlists for s in p.songs)
        stopping = downloading and self._tasks["download"][1].cancel.is_set()
        self.btn_download.setText(" " + tr("stop" if downloading else "download"))
        self.btn_download.setToolTip(tr("stop_tip" if downloading else "download_tip"))
        self.btn_download.setIcon(self.icon("stop" if downloading else "download", "accent_text", 20))
        self.btn_download.setEnabled((downloading and not stopping) or (not downloading and pending and not self.running("update")))
        self.btn_export.setEnabled(not exporting)
        self.btn_sp_cancel.setVisible(exporting)
        for widget in (self.edit_id, self.edit_secret, self.chk_own, self.chk_liked, self.btn_forget, *self.mode_radios.values()):
            widget.setEnabled(not exporting)
        self.btn_txt_dir.setEnabled(not exporting)
        self.btn_update.setEnabled(not downloading and not self.running("update") and not self.running("probe"))
        self.sp_stack.setCurrentIndex(1 if self.exports else 0)
        checked = len(self._checked_exports())
        for b in (self.btn_sp_all, self.btn_sp_none):
            b.setEnabled(bool(self.exports))
        self.btn_import.setText(" " + (tr("sp_import_n", n=checked) if checked else tr("sp_import")))
        self.btn_import.setEnabled(checked > 0)

    # ── Lista de playlists ──

    def _song_view(self, song: Song) -> tuple[str, str, str, str]:
        """(texto de estado, ícono, color, resultado) de una canción."""
        status = song.status
        if status == "downloading":
            return tr("st_downloading", pct=song.detail or "0"), "download", "accent", ""
        if status == "failed":
            error = tr(f"err_{song.code}") if i18n.has(f"err_{song.code}") else song.detail
            return tr("st_failed"), "alert", "err", error
        result = ""
        if status in ("ok", "copied") and song.detail:
            result = tr("videos", n=song.detail) if song.detail.isdigit() and core.is_url(song.line) else song.detail
        icon, color = {
            "pending": ("clock", "muted"), "queued": ("clock", "muted"), "resolving": ("search", "accent"),
            "ok": ("check", "ok"), "copied": ("copy", "ok"), "skipped": ("check", "muted"), "cancelled": ("stop", "warn"),
        }[status]
        return tr(f"st_{status}"), icon, color, result

    def refresh_song(self, pl: int, i: int) -> None:
        song = self.playlists[pl].songs[i]
        item = self.tree.topLevelItem(pl).child(i)
        text, icon, color, result = self._song_view(song)
        item.setText(COL_NAME, song.line)
        item.setText(COL_RESULT, result)
        item.setToolTip(COL_RESULT, result)
        item.setForeground(COL_RESULT, QBrush(QColor(self.colors["err" if song.status == "failed" else "muted"])))
        item.setText(COL_STATUS, text)
        item.setIcon(COL_STATUS, self.icon(icon, color))
        item.setForeground(COL_STATUS, QBrush(QColor(self.colors[color])))

    def refresh_playlist(self, pl: int, songs: bool = False) -> None:
        playlist = self.playlists[pl]
        item = self.tree.topLevelItem(pl)
        total = len(playlist.songs)
        done, bad = playlist.count(*DONE), playlist.count("failed")
        active = playlist.count("queued", "resolving", "downloading")
        font = item.font(COL_NAME)
        font.setBold(True)
        item.setFont(COL_NAME, font)
        item.setText(COL_NAME, playlist.name)
        item.setIcon(COL_NAME, self.icon("list", "muted"))
        folder = self.settings.dest_path() / core.safe_name(playlist.name)
        item.setToolTip(COL_NAME, tr("pl_tip", folder=pretty(folder)))
        item.setText(COL_RESULT, f"{i18n.songs(total)} · {tr('progress_of', done=done, n=total)}" if done else i18n.songs(total))
        item.setForeground(COL_RESULT, QBrush(QColor(self.colors["muted"])))
        if not total:
            text, icon, color = tr("pl_empty"), "alert", "muted"
        elif active:
            text, icon, color = tr("pl_running"), "download", "accent"
        elif bad:
            text, icon, color = (tr("pl_done_failed_one") if bad == 1 else tr("pl_done_failed", bad=bad)), "alert", "err"
        elif done == total:
            text, icon, color = tr("pl_done"), "check", "ok"
        else:
            text, icon, color = tr("st_pending"), "clock", "muted"
        item.setText(COL_STATUS, text)
        item.setIcon(COL_STATUS, self.icon(icon, color))
        item.setForeground(COL_STATUS, QBrush(QColor(self.colors[color])))
        if songs:
            for i in range(total):
                self.refresh_song(pl, i)

    def add_paths(self, paths: list[str]) -> int:
        known = {p.path for p in self.playlists}
        names = {p.name.lower() for p in self.playlists}
        files: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                files.extend(sorted(q for q in p.glob("*.txt") if q.is_file() and q.name not in core.FAILED_NAMES))
            else:
                files.append(p)
        added = skipped = 0
        for p in files:
            try:
                rp = p.resolve()
                lines = core.read_playlist(rp) if rp.is_file() and core.looks_like_text(rp) else []
            except OSError:
                lines = []
            if rp in known or not lines:
                skipped += 1
                continue
            known.add(rp)
            name, n = rp.stem, 2
            while name.lower() in names:
                name = f"{rp.stem} ({n})"
                n += 1
            names.add(name.lower())
            self.playlists.append(Playlist(rp, name, [Song(line) for line in lines]))
            item = QTreeWidgetItem()
            item.addChildren([QTreeWidgetItem() for _ in lines])
            self.tree.addTopLevelItem(item)
            self.refresh_playlist(len(self.playlists) - 1, songs=True)
            self.log(tr("log_added", name=name, songs=i18n.songs(len(lines))))
            added += 1
        if added == 1 and len(self.playlists) == 1:
            self.tree.topLevelItem(0).setExpanded(True)
        if skipped:
            self.log(tr("log_skipped_files", n=skipped), "warn")
        self.update_buttons()
        return added

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("pick_title"), str(Path.home()), tr("pick_filter"))
        if paths:
            self.tabs.setCurrentIndex(TAB_PLAYLISTS)
            self.add_paths(paths)

    def remove_selected(self) -> None:
        if self.running("download"):
            return
        rows = sorted({self.tree.indexOfTopLevelItem(i) for i in self.tree.selectedItems() if i.parent() is None}, reverse=True)
        for row in rows:
            self.tree.takeTopLevelItem(row)
            del self.playlists[row]
        self.update_buttons()

    def clear_list(self) -> None:
        if self.running("download"):
            return
        self.tree.clear()
        self.playlists.clear()
        self.update_buttons()

    def _open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_item(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.parent() is None:
            folder = self.settings.dest_path() / core.safe_name(self.playlists[self.tree.indexOfTopLevelItem(item)].name)
            if folder.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_destination(self) -> None:
        self._open_path(self.settings.dest_path())

    def pick_destination(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("dest_pick"), str(self.settings.dest_path()))
        if chosen:
            self._set("dest", chosen)
            self._refresh_paths()
            for index in range(len(self.playlists)):
                self.refresh_playlist(index)
            self.log(tr("log_dest", dest=pretty(Path(chosen))))

    def pick_txt_dir(self) -> None:
        current = self.settings.txt_path()
        current.mkdir(parents=True, exist_ok=True)
        chosen = QFileDialog.getExistingDirectory(self, tr("txt_pick"), str(current))
        if chosen:
            self._set("txt_dir", chosen)
            self._refresh_paths()
            self.log(tr("log_txt_dir", dest=pretty(Path(chosen))))
            self._load_existing_exports()
            self.update_buttons()

    # ── Descargas ──

    def toggle_download(self) -> None:
        if self.running("download"):
            self.cancel_task("download")
            self.set_status("status_stopping")
            self.log(tr("log_stopping"), "warn")
            self.update_buttons()
        else:
            self.start_download()

    def start_download(self) -> None:
        if self.running("update"):
            return
        jobs = []
        for index, playlist in enumerate(self.playlists):
            indices = [i for i, s in enumerate(playlist.songs) if s.status not in DONE]
            if indices:
                jobs.append(core.Job(index, playlist.name, [s.line for s in playlist.songs], indices))
        total = sum(len(j.indices) for j in jobs)
        if not total:
            self.log(tr("log_dl_nothing"), "muted")
            return
        s = self.settings
        options = core.Options(
            dest=s.dest_path(), parallel=s.parallel, audio_format=s.audio_format, metadata=s.metadata, cover=s.cover,
            skip_existing=s.skip_existing, failed_file=s.failed_file, ytmusic=s.ytmusic, artist_folders=s.artist_folders,
            track_numbers=s.track_numbers, sponsorblock=s.sponsorblock, failed_name=tr("failed_name"),
            unknown_artist=tr("unknown_artist"),
        )
        for job in jobs:
            for i in job.indices:
                song = self.playlists[job.index].songs[i]
                song.status, song.detail, song.code = "queued", "", ""
            self.refresh_playlist(job.index, songs=True)
        self._run = {"total": total, "done": 0, "bad": 0, "ok": 0, "skipped": 0}
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.show()
        self._download_status()
        self.log(tr("log_dl_start", songs=i18n.songs(total), dest=pretty(options.dest), p=options.parallel,
                    fmt=options.audio_format.upper()), "accent")

        def work(emit, cancel):
            options.ffmpeg = core.find_ffmpeg()
            engine = core.Engine(core.YtDlpBackend(updater.module(), options), options, emit, cancel)
            engine.run(jobs)

        self.start_task("download", work, self._download_event, self._download_done)

    def autorun(self) -> None:
        """Descarga lo cargado y cierra la app al terminar (MUSIC_DLP_AUTORUN, para pruebas)."""
        self._autorun = True
        QTimer.singleShot(0, self.start_download)

    def _download_status(self) -> None:
        r = self._run
        self.set_status("status_downloading_bad" if r["bad"] else "status_downloading", {"done": r["done"], "n": r["total"], "bad": r["bad"]})

    def _download_event(self, kind: str, d: dict) -> None:
        playlist = self.playlists[d["pl"]]
        if kind == "playlist":
            if self._tasks["download"][1].cancel.is_set():
                return
            self.log(tr("log_pl_done", pl=playlist.name, ok=d["ok"], skipped=d["skipped"], bad=d["failed"]), "err" if d["failed"] else "ok")
            if d["failed_path"]:
                self.log(tr("log_failed_file", pl=playlist.name, path=pretty(d["failed_path"])), "warn")
            return
        song = playlist.songs[d["i"]]
        song.status, song.detail, song.code = d["status"], d["detail"], d["code"]
        self.refresh_song(d["pl"], d["i"])
        if song.status not in FINAL:
            if song.status == "resolving":
                self.refresh_playlist(d["pl"])
            return
        self.refresh_playlist(d["pl"])
        r = self._run
        if song.status != "cancelled":
            r["done"] += 1
            self.progress.setValue(r["done"])
        _text, _icon, _color, result = self._song_view(song)
        if song.status == "failed":
            r["bad"] += 1
            self.log(tr("log_song_failed", pl=playlist.name, line=song.line, error=result), "err")
        elif song.status == "ok":
            r["ok"] += 1
            self.log(tr("log_song_ok", pl=playlist.name, line=song.line, title=result), "ok")
        elif song.status == "copied":
            r["ok"] += 1
            self.log(tr("log_song_copied", pl=playlist.name, line=song.line), "ok")
        elif song.status == "skipped":
            r["skipped"] += 1
            self.log(tr("log_song_skipped", pl=playlist.name, line=song.line), "muted")
        if not self._tasks["download"][1].cancel.is_set():
            self._download_status()

    def _download_done(self, _result, error) -> None:
        self.progress.hide()
        r = self._run
        for index, playlist in enumerate(self.playlists):
            for song in playlist.songs:
                if song.status in ("queued", "resolving", "downloading"):
                    song.status, song.detail = "cancelled", ""
            self.refresh_playlist(index, songs=True)
        if error:
            self.log(tr("log_dl_error", error=str(error)), "err")
        elif r["done"] < r["total"]:
            self.log(tr("log_dl_cancelled", ok=r["ok"], bad=r["bad"], left=r["total"] - r["done"]), "warn")
        else:
            self.log(tr("log_dl_done", ok=r["ok"], skipped=r["skipped"], bad=r["bad"]), "err" if r["bad"] else "ok")
        self.set_status("status_ready")
        if self._autorun:
            print(self.console.toPlainText(), flush=True)
            QTimer.singleShot(0, self.close)

    # ── Credenciales ──

    def _load_credentials(self) -> None:
        try:
            self.creds = self.vault.load()
        except vault.VaultError as exc:
            self._vault_failed(exc)
        self.edit_id.setText(self.creds.get("client_id", ""))
        self.edit_secret.setText(self.creds.get("client_secret", ""))

    def _vault_failed(self, exc: Exception) -> None:
        """El llavero no está disponible: seguir solo en memoria sin cambiar el ajuste guardado."""
        self.log(tr("log_vault_error", detail=str(exc) or type(exc).__name__), "warn")
        self.vault = vault.Vault("memory", settings_mod.config_dir())
        self._refresh_store_label()

    def _save_credentials(self) -> None:
        try:
            self.vault.save(self.creds)
        except vault.VaultError as exc:
            if self.vault.mode == "keyring":
                self._vault_failed(exc)
            else:
                self.log(tr("log_vault_save_error", detail=str(exc)), "err")

    def _mode_toggled(self, index: int, checked: bool) -> None:
        mode = settings_mod.CRED_MODES[index]
        if not checked or mode == self.settings.cred_mode and self.vault.mode == mode:
            return
        fresh = vault.Vault(mode, settings_mod.config_dir())
        try:
            fresh.save(self.creds) if self.creds else fresh.clear()
        except vault.VaultError as exc:
            self.log(tr("log_vault_error", detail=str(exc) or type(exc).__name__), "warn")
            self.mode_group.blockSignals(True)
            self.mode_radios[self.settings.cred_mode].setChecked(True)
            self.mode_group.blockSignals(False)
            return
        for other in ("keyring", "file"):  # no dejar copias en el almacén anterior
            if other != mode:
                try:
                    vault.Vault(other, settings_mod.config_dir()).clear()
                except vault.VaultError:
                    pass
        self.vault = fresh
        self._set("cred_mode", mode)
        self._refresh_store_label()
        self.log(tr("log_mode", mode=tr(f"sec_{mode}")))

    def forget_credentials(self) -> None:
        self.creds = {}
        vault.Vault("file", settings_mod.config_dir()).clear()
        if self.vault.mode == "keyring" or self.settings.cred_mode == "keyring":
            try:
                vault.Vault("keyring", settings_mod.config_dir()).clear()
            except vault.VaultError:
                pass
        self.vault.clear() if self.vault.mode == "memory" else None
        self.edit_id.clear()
        self.edit_secret.clear()
        self.log(tr("log_forgotten"), "ok")

    def _toggle_secret(self, shown: bool) -> None:
        self.edit_secret.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        self.btn_show.setText(tr("hide") if shown else tr("show"))

    def _copy_uri(self) -> None:
        QGuiApplication.clipboard().setText(spotify.REDIRECT_URI)
        self.log(tr("sp_uri_copied"), "muted")

    # ── Spotify ──

    def export_spotify(self) -> None:
        if self.running("spotify"):
            return
        client_id, secret = self.edit_id.text().strip(), self.edit_secret.text().strip()
        if not client_id or not secret:
            self.log(tr("log_sp_need"), "warn")
            (self.edit_id if not client_id else self.edit_secret).setFocus()
            return
        token = self.creds.get("token")
        if self.creds.get("client_id") != client_id:
            token = None
        self.creds = {"client_id": client_id, "client_secret": secret, **({"token": token} if token else {})}
        self._save_credentials()
        folder = self.settings.txt_path()
        own_only, liked, liked_name = self.settings.own_only, self.settings.include_liked, tr("liked_name")

        def work(emit, cancel):
            client = spotify.Client(client_id, secret, token, on_token=lambda t: emit("token", token=t))
            for attempt in (1, 2):
                if not client.has_session():
                    emit("login")
                    spotify.login(client, cancel, lambda url: emit("open_url", url=url))
                    emit("session")
                try:
                    return spotify.export(client, folder, own_only, liked, liked_name, cancel, emit)
                except spotify.SpotifyError as exc:
                    if exc.code != "session_expired" or attempt == 2:
                        raise
                    client.token = None  # sesión vencida: autorizar otra vez

        self.set_status("status_exporting")
        self.start_task("spotify", work, self._spotify_event, self._spotify_done)

    def _spotify_event(self, kind: str, d: dict) -> None:
        if kind == "token":
            self.creds["token"] = d["token"]
            self._save_credentials()
        elif kind == "login":
            self.log(tr("log_sp_login"), "accent")
        elif kind == "open_url":
            QDesktopServices.openUrl(QUrl(d["url"]))
            self.log(tr("log_sp_url", url=d["url"]), "muted")
        elif kind == "session" and self.vault.mode != "memory":
            self.log(tr("log_sp_session"), "muted")
        elif kind == "found":
            self.log(tr("log_sp_found", n=d["n"], dest=pretty(self.settings.txt_path())), "accent")
        elif kind == "playlist_ok":
            self.log(tr("log_sp_ok", name=d["name"], songs=i18n.songs(d["n"]), file=d["file"]), "ok")
        elif kind == "playlist_failed":
            self.log(tr("log_sp_failed", **d), "err")

    def _spotify_done(self, result, error) -> None:
        self.set_status("status_ready")
        if error:
            if isinstance(error, spotify.SpotifyError):
                key = f"sp_err_{error.code}"
                text = tr(key, status=error.status, detail=error.detail) if i18n.has(key) else tr("sp_err_other", detail=str(error))
                if error.code in ("session_expired", "bad_credentials"):
                    self.creds.pop("token", None)
                    self._save_credentials()
            else:
                text = tr("sp_err_other", detail=f"{type(error).__name__}: {error}")
            self.log(text, "warn" if getattr(error, "code", "") == "cancelled" else "err")
            return
        self._show_exports([(e.name, e.path, e.songs) for e in result])
        self.log(tr("log_sp_done", n=len(result)), "ok")
        self.tabs.setCurrentIndex(TAB_SPOTIFY)

    def _load_existing_exports(self) -> None:
        folder = self.settings.txt_path()
        found = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.txt"), key=lambda p: p.name.lower()):
                try:
                    found.append((path.stem, path, len(core.read_playlist(path))))
                except OSError:
                    continue
        self._show_exports(found)

    def _show_exports(self, exports: list[tuple[str, Path, int]]) -> None:
        self.exports = exports
        self.sp_tree.blockSignals(True)
        self.sp_tree.clear()
        for name, _path, songs in exports:
            item = QTreeWidgetItem([name, str(songs)])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if songs else Qt.CheckState.Unchecked)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.sp_tree.addTopLevelItem(item)
        self.sp_tree.blockSignals(False)
        self.update_buttons()

    def _checked_exports(self) -> list[Path]:
        return [
            self.exports[i][1] for i in range(self.sp_tree.topLevelItemCount())
            if self.sp_tree.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        ]

    def _check_exports(self, checked: bool) -> None:
        self.sp_tree.blockSignals(True)
        for i in range(self.sp_tree.topLevelItemCount()):
            self.sp_tree.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.sp_tree.blockSignals(False)
        self.update_buttons()

    def import_exports(self) -> None:
        paths = [str(p) for p in self._checked_exports()]
        if paths:
            added = self.add_paths(paths)
            self.log(tr("log_sp_imported", n=added), "ok")
            self.tabs.setCurrentIndex(TAB_PLAYLISTS)

    # ── yt-dlp ──

    @staticmethod
    def _probe(_emit, _cancel) -> dict:
        version = updater.current_version()
        return {
            "version": version,
            "origin": "user" if updater.user_version() == version else "bundled",
            "ffmpeg": core.find_ffmpeg(),
            "deno": shutil.which("deno"),
        }

    def _probe_done(self, result, error) -> None:
        if error:
            self.log(f"yt-dlp: {error}", "err")
            return
        self._yt_info = (result["version"], result["origin"])
        self._refresh_yt_label()
        self.log(tr("log_ytdlp", version=result["version"], origin=tr(f"origin_{result['origin']}")), "muted")
        if result["ffmpeg"]:
            self.log(tr("log_ffmpeg", path=pretty(Path(result["ffmpeg"]))), "muted")
        else:
            self.log(tr("log_no_ffmpeg"), "err")
        if not result["deno"]:
            self.log(tr("log_no_deno"), "warn")

    def update_ytdlp(self) -> None:
        if self.running("download"):
            self.log(tr("log_yt_busy"), "warn")
            return
        if self.running("update"):
            return
        self.log(tr("log_yt_check"), "accent")
        self.set_status("status_updating")
        before = self._yt_info[0] if self._yt_info else ""

        def done(result, error) -> None:
            self.set_status("status_ready")
            if error:
                key = f"up_err_{getattr(error, 'code', '')}"
                text = tr(key, detail=getattr(error, "detail", "")) if i18n.has(key) else f"{type(error).__name__}: {error}"
                self.log(text, "err")
                return
            if result != before:
                self._yt_info = (result, "user")
                self._refresh_yt_label()
                self.log(tr("log_yt_updated", version=result), "ok")
            else:
                self.log(tr("log_yt_latest", version=result), "ok")

        self.start_task("update", lambda emit, _cancel: updater.update(emit), self._update_event, done)

    def _update_event(self, kind: str, d: dict) -> None:
        if kind == "versions":
            self.log(tr("log_yt_versions", **d), "muted")
        elif kind == "downloading":
            self.log(tr("log_yt_downloading", **d), "muted")

    # ── Arrastrar y soltar ──

    def _set_drop_active(self, active: bool) -> None:
        self.drop.setProperty("active", "true" if active else "false")
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.tabs.setCurrentIndex(TAB_PLAYLISTS)
            self._set_drop_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)

    def dropEvent(self, event) -> None:
        self._set_drop_active(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    def closeEvent(self, event) -> None:
        for _thread, worker in self._tasks.values():
            worker.cancel.set()
        stuck = False
        for thread, _worker in list(self._tasks.values()):
            thread.quit()
            stuck = not thread.wait(6000) or stuck
        self.creds = {}
        super().closeEvent(event)
        if stuck:  # una descarga no respondió a tiempo: no dejar el proceso colgado
            os._exit(0)
