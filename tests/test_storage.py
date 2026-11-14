# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import io
import json
import stat
import zipfile

import pytest

from music_dlp import settings, updater, vault


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def get_password(self, service, account):
        return self.items.get((service, account))

    def set_password(self, service, account, value):
        self.items[(service, account)] = value

    def delete_password(self, service, account):
        del self.items[(service, account)]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSIC_DLP_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("MUSIC_DLP_DATA", str(tmp_path / "data"))


def test_settings_round_trip_and_defaults(tmp_path):
    s = settings.load()
    assert (s.parallel, s.audio_format, s.cred_mode, s.artist_folders) == (4, "mp3", "keyring", False)
    assert s.txt_path() == tmp_path / "data" / "playlists"
    s.parallel, s.dest, s.artist_folders = 8, str(tmp_path / "musica"), True
    settings.save(s)
    again = settings.load()
    assert (again.parallel, again.dest_path(), again.artist_folders) == (8, tmp_path / "musica", True)


def test_settings_tolerate_bad_values(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.json").write_text(json.dumps({"parallel": 99, "audio_format": "wav", "cover": "sí", "cred_mode": "nube", "extra": 1}))
    s = settings.load()
    assert (s.parallel, s.audio_format, s.cover, s.cred_mode) == (16, "mp3", True, "keyring")
    (tmp_path / "config" / "config.json").write_text("roto")
    assert settings.load().parallel == 4


def test_vault_file_mode_is_private(tmp_path):
    v = vault.Vault("file", tmp_path)
    assert v.load() == {}
    v.save({"client_id": "a", "client_secret": "b"})
    assert stat.S_IMODE((tmp_path / vault.FILE_NAME).stat().st_mode) == 0o600
    assert vault.Vault("file", tmp_path).load() == {"client_id": "a", "client_secret": "b"}
    v.clear()
    assert not (tmp_path / vault.FILE_NAME).exists()


def test_vault_keyring_and_memory_modes(tmp_path):
    ring = FakeKeyring()
    v = vault.Vault("keyring", tmp_path, ring)
    v.save({"client_id": "a"})
    assert json.loads(ring.items[(vault.SERVICE, vault.ACCOUNT)]) == {"client_id": "a"}
    assert vault.Vault("keyring", tmp_path, ring).load() == {"client_id": "a"}
    assert not list(tmp_path.iterdir())
    v.clear()
    v.clear()  # borrar dos veces no falla
    assert ring.items == {}

    m = vault.Vault("memory", tmp_path)
    m.save({"client_id": "a"})
    assert m.load() == {"client_id": "a"} and not list(tmp_path.iterdir())


def test_wipe_all(tmp_path):
    ring = FakeKeyring()
    vault.Vault("file", tmp_path).save({"x": 1})
    vault.Vault("keyring", tmp_path, ring).save({"x": 1})
    vault.wipe_all(tmp_path, ring)
    assert ring.items == {} and not (tmp_path / vault.FILE_NAME).exists()


def wheel(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    data = buf.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def pypi(version, data, sha, requires=()):
    return {"info": {"version": version, "requires_dist": list(requires)},
            "urls": [{"packagetype": "sdist", "filename": "x.tar.gz", "url": "https://f/x.tar.gz", "digests": {"sha256": "0"}},
                     {"packagetype": "bdist_wheel", "filename": f"pkg-{version}-py3-none-any.whl", "url": f"https://f/pkg-{version}.whl", "digests": {"sha256": sha}}]}


def test_version_helpers():
    assert updater.version_tuple("2026.10.26") > updater.version_tuple("2026.9.30")
    assert updater.ejs_pin({"info": {"requires_dist": ['mutagen; extra == "default"', 'yt-dlp-ejs==0.8.0; extra == "default"']}}) == "0.8.0"
    assert updater.ejs_pin({"info": {}}) == ""
    assert updater.user_version() == ""


def test_update_installs_newer_version_and_loads_it(tmp_path):
    current = updater.current_version()
    newer = "2999.01.01"
    data, sha = wheel({"yt_dlp/__init__.py": "from . import version\n", "yt_dlp/version.py": f"__version__ = '{newer}'\n"})
    ejs, ejs_sha = wheel({"yt_dlp_ejs/__init__.py": "version = '9'\n"})
    answers = {
        updater.PYPI.format(name="yt-dlp"): json.dumps(pypi(newer, data, sha, ['yt-dlp-ejs==9.0; extra == "default"'])).encode(),
        updater.PYPI_VERSION.format(name="yt-dlp-ejs", version="9.0"): json.dumps(pypi("9.0", ejs, ejs_sha)).encode(),
        f"https://f/pkg-{newer}.whl": data,
        "https://f/pkg-9.0.whl": ejs,
    }
    events = []
    try:
        assert updater.update(lambda k, **d: events.append((k, d)), answers.__getitem__) == newer
        assert events[0] == ("versions", {"current": current, "latest": newer})
        assert updater.user_version() == newer
        assert (tmp_path / "data" / "yt-dlp" / "yt_dlp_ejs" / "__init__.py").is_file()
        assert not (tmp_path / "data" / "yt-dlp.new").exists()
        # Ya está al día: no baja nada más
        assert updater.update(lambda *_a, **_k: None, answers.__getitem__) == newer
    finally:
        import shutil
        shutil.rmtree(tmp_path / "data", ignore_errors=True)
        assert updater.module(reload=True).version.__version__ == current


def test_update_rejects_bad_checksum(tmp_path):
    data, _sha = wheel({"yt_dlp/version.py": "__version__ = '2999.01.01'\n"})
    answers = {updater.PYPI.format(name="yt-dlp"): json.dumps(pypi("2999.01.01", data, "0" * 64)).encode(), "https://f/pkg-2999.01.01.whl": data}
    with pytest.raises(updater.UpdateError) as err:
        updater.update(lambda *_a, **_k: None, answers.__getitem__)
    assert err.value.code == "checksum"
    assert updater.user_version() == "" and not (tmp_path / "data" / "yt-dlp.new").exists()


def test_update_when_already_latest():
    current = updater.current_version()
    answers = {updater.PYPI.format(name="yt-dlp"): json.dumps(pypi(current, b"", "0")).encode()}
    assert updater.update(lambda *_a, **_k: None, answers.__getitem__) == current
