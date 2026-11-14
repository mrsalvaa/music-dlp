# SPDX-License-Identifier: GPL-3.0-or-later
import threading
from pathlib import Path

import pytest

from music_dlp import core


class FakeBackend:
    """Simula yt-dlp: "x" no existe, "boom" falla, "a+b" es una URL con dos videos."""

    def __init__(self, ext="mp3"):
        self.downloads = []
        self.resolved = []
        self.ext = ext
        self.lock = threading.Lock()

    def resolve(self, line, cancel):
        with self.lock:
            self.resolved.append(line)
        if line == "x":
            return []
        if line == "boom":
            raise core.DownloadFailed("ytdlp", "video no disponible")
        return [core.Track(f"yt:{part.lower()}", f"https://example/{part}") for part in line.split("+")]

    def download(self, track, folder, names, progress, cancel):
        with self.lock:
            self.downloads.append(track.key)
        progress(50)
        title = track.key.split(":")[1].upper()
        sub, stem = names("Artista", "Canal", title)
        path = folder / sub / f"{stem}.{self.ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(track.key)
        return core.Downloaded(path, "Artista", "Canal", title)


def run(tmp_path, jobs, backend=None, **options):
    backend = backend or FakeBackend(options.get("audio_format", "mp3"))
    events = []
    lock = threading.Lock()

    def emit(kind, **data):
        with lock:
            events.append((kind, data))

    engine = core.Engine(backend, core.Options(dest=tmp_path, **options), emit)
    engine.run(jobs)
    return backend, events


def job(index, name, lines):
    return core.Job(index, name, lines, list(range(len(lines))))


def final(events, pl=0):
    return {d["i"]: d["status"] for k, d in events if k == "song" and d["pl"] == pl and d["status"] not in ("resolving", "downloading")}


def test_parse_playlist_ignores_blank_comments_and_repeats():
    text = "﻿# lista\nUno - A\n\n  Dos - B  \nUno - A\nhttps://x/y\n"
    assert core.parse_playlist(text.lstrip("﻿")) == ["Uno - A", "Dos - B", "https://x/y"]


def test_read_playlist_handles_bom(tmp_path):
    f = tmp_path / "l.txt"
    f.write_bytes("﻿Uno\nDos\n".encode("utf-8"))
    assert core.read_playlist(f) == ["Uno", "Dos"]


@pytest.mark.parametrize("raw,expected", [("Rock: lo mejor?", "Rock_ lo mejor_"), ("  ..  ", "untitled"), ("a/b\\c", "a_b_c"), ("fin. ", "fin")])
def test_safe_name(raw, expected):
    assert core.safe_name(raw) == expected


def test_looks_like_text(tmp_path):
    (tmp_path / "a.txt").write_text("hola")
    (tmp_path / "b.bin").write_bytes(b"\x00\x01")
    assert core.looks_like_text(tmp_path / "a.txt")
    assert not core.looks_like_text(tmp_path / "b.bin")


def test_songs_go_flat_into_the_playlist_folder(tmp_path):
    _, events = run(tmp_path, [job(0, "play2", ["A", "B"])])
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.mp3"))
    assert files == ["play2/Artista - A.mp3", "play2/Artista - B.mp3"]
    assert [p for p in (tmp_path / "play2").iterdir() if p.is_dir()] == []
    assert final(events) == {0: "ok", 1: "ok"}


def test_artist_folders_and_track_numbers(tmp_path):
    run(tmp_path, [job(0, "play2", ["A", "B"])], artist_folders=True, track_numbers=True)
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.mp3"))
    assert files == ["play2/Artista/01 - A.mp3", "play2/Artista/02 - B.mp3"]


def test_second_run_skips_without_resolving(tmp_path):
    run(tmp_path, [job(0, "p", ["A", "B"])])
    backend, events = run(tmp_path, [job(0, "p", ["A", "B"])])
    assert backend.resolved == [] and backend.downloads == []
    assert final(events) == {0: "skipped", 1: "skipped"}


def test_deleted_file_is_downloaded_again(tmp_path):
    run(tmp_path, [job(0, "p", ["A"])])
    (tmp_path / "p" / "Artista - A.mp3").unlink()
    backend, events = run(tmp_path, [job(0, "p", ["A"])])
    assert backend.downloads == ["yt:a"] and final(events) == {0: "ok"}


def test_skip_disabled_downloads_again(tmp_path):
    run(tmp_path, [job(0, "p", ["A"])])
    backend, _ = run(tmp_path, [job(0, "p", ["A"])], skip_existing=False)
    assert backend.downloads == ["yt:a"]


def test_song_in_another_playlist_is_copied(tmp_path):
    run(tmp_path, [job(0, "uno", ["A"])])
    backend, events = run(tmp_path, [job(0, "dos", ["A", "B"])])
    assert backend.downloads == ["yt:b"]
    assert final(events) == {0: "copied", 1: "ok"}
    assert (tmp_path / "dos" / "Artista - A.mp3").read_text() == "yt:a"


def test_other_format_is_not_copied(tmp_path):
    run(tmp_path, [job(0, "uno", ["A"])])
    backend, _ = run(tmp_path, [job(0, "dos", ["A"])], audio_format="opus")
    assert backend.downloads == ["yt:a"]
    assert (tmp_path / "dos" / "Artista - A.opus").is_file()


def test_same_song_in_two_playlists_downloads_once(tmp_path):
    backend, events = run(tmp_path, [job(0, "uno", ["A"]), job(1, "dos", ["A"])], parallel=4)
    assert backend.downloads == ["yt:a"]
    assert sorted([final(events, 0)[0], final(events, 1)[0]]) == ["copied", "ok"]


def test_failed_file_written_and_removed(tmp_path):
    _, events = run(tmp_path, [job(0, "p", ["A", "x", "boom"])], failed_name="fallidas.txt")
    assert final(events) == {0: "ok", 1: "failed", 2: "failed"}
    assert (tmp_path / "p" / "fallidas.txt").read_text() == "x\nboom\n"
    summary = [d for k, d in events if k == "playlist"][0]
    assert (summary["ok"], summary["failed"]) == (1, 2)
    codes = {d["i"]: d["code"] for k, d in events if k == "song" and d["status"] == "failed"}
    assert codes == {1: "no_results", 2: "ytdlp"}
    run(tmp_path, [job(0, "p", ["A"])])
    assert not (tmp_path / "p" / "fallidas.txt").exists()


def test_failed_file_can_be_disabled(tmp_path):
    run(tmp_path, [job(0, "p", ["x"])], failed_file=False)
    assert not (tmp_path / "p" / "fallidas.txt").exists()


def test_url_with_several_videos(tmp_path):
    backend, events = run(tmp_path, [job(0, "p", ["A+B"])])
    assert sorted(backend.downloads) == ["yt:a", "yt:b"]
    assert [d["detail"] for k, d in events if k == "song" and d["status"] == "ok"] == ["2"]


def test_only_requested_indices_are_processed(tmp_path):
    backend, _ = run(tmp_path, [core.Job(0, "p", ["A", "B", "C"], [1])])
    assert backend.downloads == ["yt:b"]


def test_cancel_stops_pending_songs(tmp_path):
    backend = FakeBackend()
    events = []
    engine = core.Engine(backend, core.Options(dest=tmp_path, parallel=1), lambda k, **d: events.append((k, d)))
    original = backend.download

    def download_then_cancel(*args):
        engine.stop()
        return original(*args)

    backend.download = download_then_cancel
    engine.run([job(0, "p", ["A", "B", "C"])])
    assert final(events) == {0: "ok", 1: "cancelled", 2: "cancelled"}


def test_corrupt_state_file_is_ignored(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / core.STATE_FILE).write_text("{no es json")
    backend, _ = run(tmp_path, [job(0, "p", ["A"])])
    assert backend.downloads == ["yt:a"]


def test_clean_error():
    assert core.clean_error(Exception("\x1b[0;31mERROR:\x1b[0m [youtube] abc: Video unavailable")) == "[youtube] abc: Video unavailable"
