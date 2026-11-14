# SPDX-License-Identifier: GPL-3.0-or-later
import re
import string
from pathlib import Path

from music_dlp import i18n

SRC = Path(__file__).parent.parent / "src" / "music_dlp"


def test_every_text_has_both_languages_with_the_same_fields():
    for key, (es, en) in i18n._T.items():
        assert es and en, key
        fields = [sorted(f for _t, f, _s, _c in string.Formatter().parse(text) if f) for text in (es, en)]
        assert fields[0] == fields[1], key


def test_keys_used_by_the_interface_exist():
    code = (SRC / "ui.py").read_text("utf-8")
    literal = set(re.findall(r'"((?:[a-z]+_)*[a-z0-9]+)"', code))
    used = set(re.findall(r'\btr\("([a-z0-9_]+)"', code)) | {k for k in literal if k in i18n._T}
    used |= set(re.findall(r'_(?:text|button)\([^,\n]*?"([a-z0-9_]+)"', code))
    missing = sorted(k for k in used if k and not i18n.has(k))
    assert not missing, missing
    for prefix, values in (("st_", ("pending", "queued", "resolving", "downloading", "ok", "copied", "skipped", "failed", "cancelled")),
                           ("fmt_", ("mp3", "opus", "m4a", "flac")), ("sec_", ("keyring", "file", "memory")),
                           ("sp_store_", ("keyring", "file", "memory")), ("origin_", ("bundled", "user")),
                           ("sp_err_", ("cancelled", "network", "bad_credentials", "auth_failed", "session_expired", "auth_denied",
                                        "auth_timeout", "port_busy", "forbidden", "api")),
                           ("up_err_", ("network", "checksum", "invalid"))):
        for value in values:
            assert i18n.has(prefix + value), prefix + value


def test_language_switch():
    i18n.set_language("es")
    assert i18n.tr("download") == "Descargar" and i18n.songs(1) == "1 canción" and i18n.songs(3) == "3 canciones"
    i18n.set_language("en")
    assert i18n.tr("download") == "Download" and i18n.songs(2) == "2 songs"
    i18n.set_language("xx")
    assert i18n.language() == "en"
